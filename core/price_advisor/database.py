"""SQLite and PostgreSQL-based price database with vector similarity search.

Supports both SQLite (numpy-based cosine similarity) and PostgreSQL (via pgvector extension)
depending on the configured ``PRICE_ADVISOR_DB_PROVIDER`` settings.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional, Any

import numpy as np

from .models import PriceRecord, SimilarItem
from .config import PriceAdvisorConfig

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name       TEXT NOT NULL DEFAULT '',
    item_code       TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT '',
    unit_price      REAL,
    total_price     REAL,
    quantity        REAL,
    project_name    TEXT NOT NULL DEFAULT '',
    project_type    TEXT NOT NULL DEFAULT '',
    year            INTEGER,
    region          TEXT NOT NULL DEFAULT '',
    brand           TEXT NOT NULL DEFAULT '',
    origin          TEXT NOT NULL DEFAULT '',
    material_spec   TEXT NOT NULL DEFAULT '',
    embedding       BLOB,
    source_file     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    status          TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_price_records_status ON price_records(status);
CREATE INDEX IF NOT EXISTS idx_price_records_year ON price_records(year);
CREATE INDEX IF NOT EXISTS idx_price_records_item_name ON price_records(item_name);

CREATE TABLE IF NOT EXISTS feedback_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    action          TEXT NOT NULL DEFAULT 'pending',
    suggested_price REAL,
    user_note       TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS llm_training_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              TEXT NOT NULL DEFAULT '',
    item_id             TEXT NOT NULL DEFAULT '',
    item_name           TEXT NOT NULL DEFAULT '',
    unit                TEXT NOT NULL DEFAULT '',
    input_context       TEXT NOT NULL DEFAULT '',
    output_response     TEXT NOT NULL DEFAULT '',
    suggested_price     REAL,
    confidence          REAL,
    reasoning           TEXT NOT NULL DEFAULT '',
    llm_provider        TEXT NOT NULL DEFAULT '',
    llm_model           TEXT NOT NULL DEFAULT '',
    user_action         TEXT NOT NULL DEFAULT 'pending',
    user_price          REAL,
    user_note           TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_training_log_job_item ON llm_training_log(job_id, item_id);
"""


def _get_postgres_schema(dims: int, has_vector: bool = True) -> str:
    """Generate PostgreSQL schema with dynamic vector dimension."""
    embedding_type = f"vector({dims})" if has_vector else "double precision[]"
    return f"""
CREATE TABLE IF NOT EXISTS price_records (
    id              SERIAL PRIMARY KEY,
    item_name       VARCHAR(255) NOT NULL DEFAULT '',
    item_code       VARCHAR(100) NOT NULL DEFAULT '',
    unit            VARCHAR(50) NOT NULL DEFAULT '',
    unit_price      DOUBLE PRECISION,
    total_price     DOUBLE PRECISION,
    quantity        DOUBLE PRECISION,
    project_name    VARCHAR(255) NOT NULL DEFAULT '',
    project_type    VARCHAR(100) NOT NULL DEFAULT '',
    year            INTEGER,
    region          VARCHAR(100) NOT NULL DEFAULT '',
    brand           VARCHAR(100) NOT NULL DEFAULT '',
    origin          VARCHAR(100) NOT NULL DEFAULT '',
    material_spec   TEXT NOT NULL DEFAULT '',
    embedding       {embedding_type},
    source_file     VARCHAR(255) NOT NULL DEFAULT '',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status          VARCHAR(50) NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_price_records_status ON price_records(status);
CREATE INDEX IF NOT EXISTS idx_price_records_year ON price_records(year);

CREATE TABLE IF NOT EXISTS feedback_log (
    id              SERIAL PRIMARY KEY,
    job_id          VARCHAR(100) NOT NULL,
    item_id         VARCHAR(100) NOT NULL,
    action          VARCHAR(50) NOT NULL DEFAULT 'pending',
    suggested_price DOUBLE PRECISION,
    user_note       TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS llm_training_log (
    id                  SERIAL PRIMARY KEY,
    job_id              VARCHAR(100) NOT NULL DEFAULT '',
    item_id             VARCHAR(100) NOT NULL DEFAULT '',
    item_name           VARCHAR(255) NOT NULL DEFAULT '',
    unit                VARCHAR(50) NOT NULL DEFAULT '',
    input_context       TEXT NOT NULL DEFAULT '',
    output_response     TEXT NOT NULL DEFAULT '',
    suggested_price     DOUBLE PRECISION,
    confidence          DOUBLE PRECISION,
    reasoning           TEXT NOT NULL DEFAULT '',
    llm_provider        VARCHAR(100) NOT NULL DEFAULT '',
    llm_model           VARCHAR(100) NOT NULL DEFAULT '',
    user_action         VARCHAR(50) NOT NULL DEFAULT 'pending',
    user_price          DOUBLE PRECISION,
    user_note           TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_llm_training_log_job_item ON llm_training_log(job_id, item_id);
"""


def _vector_to_blob(vector: list[float]) -> bytes:
    """Serialize a float vector to bytes for SQLite BLOB storage."""
    return np.array(vector, dtype=np.float32).tobytes()


def _blob_to_vector(blob: bytes) -> np.ndarray:
    """Deserialize a BLOB back to a numpy array."""
    return np.frombuffer(blob, dtype=np.float32)


def _vector_to_postgres(vector: list[float]) -> str:
    """Format float vector as a Postgres vector string, e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(map(str, vector)) + "]"


# ---------------------------------------------------------------------------
# Tách TÊN NHÀ THẦU khỏi cột brand.
#
# Dữ liệu lịch sử không có cột nhà thầu riêng: tên nhà thầu bị gộp vào brand
# theo dạng "Hãng (Nhà thầu)", ví dụ "Hãng X (Công ty ABC)", "Hãng Y / Hãng Z (Công ty DEF)".
# Nhưng trong ngoặc cũng có thể là VIẾT TẮT CỦA HÃNG ("Á Châu (ACIT)"), nên không
# thể lấy bừa mọi cụm trong ngoặc.
#
# Cách phân biệt (tự suy ra từ dữ liệu, KHÔNG hardcode tên nhà thầu của một dự án):
# một nhà thầu chào cho rất nhiều hãng khác nhau nên tên nó xuất hiện trong ngoặc
# ở NHIỀU brand khác nhau; còn viết tắt của hãng chỉ đi kèm đúng hãng đó.
# ---------------------------------------------------------------------------
_PAREN = re.compile(r"\(([^)]*)\)")
_EMPTY_BRAND = {"", "n/a", "na", "none", "null", "-"}
# Ngưỡng: tên phải xuất hiện trong ngoặc ở ít nhất ngần này brand khác nhau.
_MIN_BRANDS_FOR_BIDDER = 5


def build_bidder_vocabulary(brands: Iterable[str]) -> frozenset[str]:
    """Suy ra tập tên nhà thầu (dạng casefold) từ danh sách brand phân biệt."""
    seen: dict[str, set[str]] = {}
    for brand in brands:
        raw = str(brand or "")
        for token in _PAREN.findall(raw):
            name = token.strip()
            if name:
                seen.setdefault(name.casefold(), set()).add(raw)
    return frozenset(
        name for name, brand_set in seen.items()
        if len(brand_set) >= _MIN_BRANDS_FOR_BIDDER
    )


def split_brand_bidder(brand: str, vocabulary: frozenset[str]) -> tuple[str, str]:
    """Trả về (tên hãng, tên nhà thầu) tách từ một giá trị brand."""
    raw = str(brand or "").strip()
    if raw.casefold() in _EMPTY_BRAND:
        return "", ""

    for token in _PAREN.findall(raw):
        name = token.strip()
        if name and name.casefold() in vocabulary:
            remainder = raw.replace(f"({token})", " ")
            remainder = re.sub(r"\s{2,}", " ", remainder).strip(" /+,-")
            return remainder, name

    # Brand chính là tên nhà thầu (không kèm hãng nào).
    if raw.casefold() in vocabulary:
        return "", raw
    return raw, ""


class PriceDatabase:
    """Dual-mode Database store supporting SQLite and PostgreSQL with pgvector."""

    def __init__(self, db_path: str | Path, config: Optional[PriceAdvisorConfig] = None) -> None:
        self._config = config or PriceAdvisorConfig.from_env()
        self._path = Path(db_path)
        self._local = threading.local()
        self._provider = self._config.db_provider
        self.has_pgvector = False
        self._bidder_vocab: Optional[frozenset[str]] = None

        if self._provider == "postgres" and not HAS_POSTGRES:
            raise ImportError(
                "Cài gói 'psycopg2-binary' để kết nối PostgreSQL: "
                "pip install psycopg2-binary"
            )

        if self._provider == "sqlite":
            self._path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self) -> None:
        """Initialize appropriate database schema."""
        if self._provider == "sqlite":
            conn = self._sqlite_conn()
            conn.executescript(_SQLITE_SCHEMA)
            conn.commit()
        else:
            conn = self._postgres_conn()
            has_vector = False

            # Step 1: Try to create the vector extension in its own transaction
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                has_vector = True
            except Exception:
                logger.warning(
                    "pgvector extension is not available in PostgreSQL. "
                    "Falling back to double precision[] for embeddings (keyword search only)."
                )
            finally:
                conn.autocommit = False

            # Step 2: Verify the vector type actually exists
            if has_vector:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM pg_type WHERE typname = 'vector'")
                    if not cur.fetchone():
                        has_vector = False

            self.has_pgvector = has_vector

            # Step 3: Create all tables in one transaction
            with conn.cursor() as cur:
                cur.execute(_get_postgres_schema(self._config.embedding_dimensions, has_vector=has_vector))
            conn.commit()

    def _sqlite_conn(self) -> sqlite3.Connection:
        """Thread-local SQLite connection."""
        if not hasattr(self._local, "sqlite_conn") or self._local.sqlite_conn is None:
            self._local.sqlite_conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._local.sqlite_conn.row_factory = sqlite3.Row
        return self._local.sqlite_conn

    def _postgres_conn(self) -> Any:
        """Thread-local PostgreSQL connection."""
        if not hasattr(self._local, "postgres_conn") or self._local.postgres_conn is None:
            self._local.postgres_conn = psycopg2.connect(
                host=self._config.db_host,
                port=self._config.db_port,
                dbname=self._config.db_name,
                user=self._config.db_user,
                password=self._config.db_password,
                cursor_factory=RealDictCursor,
            )
        return self._local.postgres_conn

    def _conn(self) -> Any:
        if self._provider == "sqlite":
            return self._sqlite_conn()
        return self._postgres_conn()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert_records(self, records: list[PriceRecord]) -> int:
        """Bulk insert price records. Returns the count of inserted rows."""
        if not records:
            return 0
        conn = self._conn()
        inserted = 0

        if self._provider == "sqlite":
            for record in records:
                embedding_blob = _vector_to_blob(record.embedding) if record.embedding else None
                conn.execute(
                    """
                    INSERT INTO price_records
                        (item_name, item_code, unit, unit_price, total_price, quantity,
                         project_name, project_type, year, region, brand, origin,
                         material_spec, embedding, source_file, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.item_name, record.item_code, record.unit,
                        record.unit_price, record.total_price, record.quantity,
                        record.project_name, record.project_type, record.year, record.region,
                        record.brand, record.origin, record.material_spec,
                        embedding_blob, record.source_file, record.status,
                    ),
                )
                inserted += 1
            conn.commit()
        else:
            with conn.cursor() as cur:
                for record in records:
                    if record.embedding:
                        embedding_val = _vector_to_postgres(record.embedding) if self.has_pgvector else record.embedding
                    else:
                        embedding_val = None
                    cur.execute(
                        """
                        INSERT INTO price_records
                            (item_name, item_code, unit, unit_price, total_price, quantity,
                             project_name, project_type, year, region, brand, origin,
                             material_spec, embedding, source_file, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.item_name, record.item_code, record.unit,
                            record.unit_price, record.total_price, record.quantity,
                            record.project_name, record.project_type, record.year, record.region,
                            record.brand, record.origin, record.material_spec,
                            embedding_val, record.source_file, record.status,
                        ),
                    )
                    inserted += 1
            conn.commit()
        return inserted

    def log_llm_query(
        self,
        job_id: str,
        item_id: str,
        item_name: str,
        unit: str,
        input_context: dict,
        output_response: dict,
        suggested_price: Optional[float],
        confidence: float,
        reasoning: str,
        llm_provider: str,
        llm_model: str,
    ) -> None:
        """Log the LLM query context and response for local LLM fine-tuning."""
        conn = self._conn()
        input_str = json.dumps(input_context, ensure_ascii=False)
        output_str = json.dumps(output_response, ensure_ascii=False)

        if self._provider == "sqlite":
            conn.execute(
                """
                INSERT INTO llm_training_log
                    (job_id, item_id, item_name, unit, input_context, output_response,
                     suggested_price, confidence, reasoning, llm_provider, llm_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id, item_id, item_name, unit, input_str, output_str,
                    suggested_price, confidence, reasoning, llm_provider, llm_model,
                ),
            )
            conn.commit()
        else:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_training_log
                        (job_id, item_id, item_name, unit, input_context, output_response,
                         suggested_price, confidence, reasoning, llm_provider, llm_model)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id, item_id, item_name, unit, input_str, output_str,
                        suggested_price, confidence, reasoning, llm_provider, llm_model,
                    ),
                )
            conn.commit()

    def log_feedback(self, job_id: str, item_id: str, action: str,
                     suggested_price: Optional[float] = None, note: str = "") -> None:
        """Record user Accept/Reject feedback for a suggestion and update training log."""
        conn = self._conn()

        if self._provider == "sqlite":
            # 1. Log to the old feedback_log table
            conn.execute(
                "INSERT INTO feedback_log (job_id, item_id, action, suggested_price, user_note) "
                "VALUES (?, ?, ?, ?, ?)",
                (job_id, item_id, action, suggested_price, note),
            )
            # 2. Update the training log with the user's action
            conn.execute(
                """
                UPDATE llm_training_log
                SET user_action = ?, user_price = ?, user_note = ?
                WHERE job_id = ? AND item_id = ?
                """,
                (action, suggested_price if action == "accepted" else None, note, job_id, item_id),
            )
            conn.commit()
        else:
            with conn.cursor() as cur:
                # 1. Log to feedback_log
                cur.execute(
                    """
                    INSERT INTO feedback_log (job_id, item_id, action, suggested_price, user_note)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (job_id, item_id, action, suggested_price, note),
                )
                # 2. Update llm_training_log
                cur.execute(
                    """
                    UPDATE llm_training_log
                    SET user_action = %s, user_price = %s, user_note = %s
                    WHERE job_id = %s AND item_id = %s
                    """,
                    (action, suggested_price if action == "accepted" else None, note, job_id, item_id),
                )
            conn.commit()

    def _bidder_vocabulary(self) -> frozenset[str]:
        """Tập tên nhà thầu suy ra từ toàn bộ brand trong CSDL (đọc 1 lần, cache)."""
        if self._bidder_vocab is not None:
            return self._bidder_vocab
        brands: list[str] = []
        try:
            conn = self._conn()
            if self._provider == "sqlite":
                brands = [
                    row[0] for row in conn.execute(
                        "SELECT DISTINCT brand FROM price_records WHERE brand IS NOT NULL"
                    )
                ]
            else:
                with conn.cursor() as cur:
                    cur.execute("SELECT DISTINCT brand FROM price_records WHERE brand IS NOT NULL")
                    brands = [row["brand"] for row in cur.fetchall()]
        except Exception as exc:
            logger.warning("Không dựng được từ vựng nhà thầu: %s", exc)
        self._bidder_vocab = build_bidder_vocabulary(brands)
        logger.info("Nhận diện %d nhà thầu từ dữ liệu giá", len(self._bidder_vocab))
        return self._bidder_vocab

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def search_similar(self, query_embedding: list[float], top_k: int = 5,
                       status: str = "active", query_text: str = "") -> list[SimilarItem]:
        """Find the most similar price records by cosine similarity or keyword search fallback."""
        conn = self._conn()

        # Check if we should use keyword search fallback
        use_keyword_search = False
        if not query_embedding:
            use_keyword_search = True
        else:
            try:
                query_vec = np.array(query_embedding, dtype=np.float32)
                if query_vec.size == 0 or np.linalg.norm(query_vec) == 0:
                    use_keyword_search = True
            except Exception:
                use_keyword_search = True

        if use_keyword_search:
            if not query_text:
                return []

            # Keyword search fallback
            # Split query_text into words for a simple search, ignoring very short words
            words = [w.strip() for w in query_text.split() if len(w.strip()) > 1]
            if not words:
                words = [query_text.strip()]

            # Multi-stage search:
            ph = "?" if self._provider == "sqlite" else "%s"
            where_clauses = [f"status = {ph}"]
            params = [status]
            rows = []

            # Stage 0: Check for technical anchors (e.g., RJ45, CAT6, UTP, STP, SWITCH, PIR, DVR, NVR, etc.)
            # If a technical anchor code is present, prioritize rows matching this technical code to avoid noise from generic words (like 'cắm')
            tech_anchors = [w for w in words if re.search(r'(?:rj45|cat[56][ae]?|utp|stp|patch|switch|router|pir|dvr|nvr|sfp|cctv|ap|hdmi|vga|fiber)', w, re.IGNORECASE)]
            if tech_anchors:
                anchor_clauses = []
                anchor_params = list(params)
                for anc in tech_anchors:
                    if self._provider == "sqlite":
                        anchor_clauses.append("(item_name LIKE ? OR material_spec LIKE ?)")
                        anchor_params.extend([f"%{anc}%", f"%{anc}%"])
                    else:
                        anchor_clauses.append("(item_name ILIKE %s OR material_spec ILIKE %s)")
                        anchor_params.extend([f"%{anc}%", f"%{anc}%"])
                
                sql_anchor = (
                    "SELECT id, item_name, item_code, unit, unit_price, total_price, "
                    "quantity, project_name, project_type, year, region, brand, origin, "
                    "material_spec, source_file, created_at, status "
                    f"FROM price_records WHERE {' AND '.join(where_clauses + anchor_clauses)} LIMIT 200"
                )
                if self._provider == "sqlite":
                    cursor = conn.execute(sql_anchor, tuple(anchor_params))
                    rows = cursor.fetchall()
                else:
                    with conn.cursor() as cur:
                        cur.execute(sql_anchor, tuple(anchor_params))
                        rows = cur.fetchall()

            # Stage 1: Try AND matching for all words (if Stage 0 yielded no rows)
            if not rows:
                and_clauses = []
                and_params = list(params)
                for word in words[:5]:
                    if self._provider == "sqlite":
                        and_clauses.append("item_name LIKE ?")
                    else:
                        and_clauses.append("item_name ILIKE %s")
                    and_params.append(f"%{word}%")
                
                sql_and = (
                    "SELECT id, item_name, item_code, unit, unit_price, total_price, "
                    "quantity, project_name, project_type, year, region, brand, origin, "
                    "material_spec, source_file, created_at, status "
                    f"FROM price_records WHERE {' AND '.join(where_clauses + and_clauses)} LIMIT 100"
                )
                if self._provider == "sqlite":
                    cursor = conn.execute(sql_and, tuple(and_params))
                    rows = cursor.fetchall()
                else:
                    with conn.cursor() as cur:
                        cur.execute(sql_and, tuple(and_params))
                        rows = cur.fetchall()

            # Stage 2: If AND returned nothing, try matching via OR with a larger LIMIT
            if not rows and len(words) > 1:
                or_clauses = []
                or_params = list(params)
                for word in words[:5]:
                    if self._provider == "sqlite":
                        or_clauses.append("item_name LIKE ?")
                    else:
                        or_clauses.append("item_name ILIKE %s")
                    or_params.append(f"%{word}%")
                
                sql_or = (
                    "SELECT id, item_name, item_code, unit, unit_price, total_price, "
                    "quantity, project_name, project_type, year, region, brand, origin, "
                    "material_spec, source_file, created_at, status "
                    f"FROM price_records WHERE {' AND '.join(where_clauses)} AND ({' OR '.join(or_clauses)}) LIMIT 500"
                )
                if self._provider == "sqlite":
                    cursor = conn.execute(sql_or, tuple(or_params))
                    rows = cursor.fetchall()
                else:
                    with conn.cursor() as cur:
                        cur.execute(sql_or, tuple(or_params))
                        rows = cur.fetchall()

            # Score them by how many words match and string similarity (token overlap)
            scored = []
            query_words_set = set(w.lower() for w in words)
            for row in rows:
                row_name = row["item_name"].lower()
                match_count = sum(1 for w in query_words_set if w in row_name)
                score = match_count / len(query_words_set) if query_words_set else 0.0
                scored.append((score, row))

            scored.sort(key=lambda x: x[0], reverse=True)
            candidate_rows = scored[:top_k]

        else:
            if self._provider == "sqlite":
                cursor = conn.execute(
                    "SELECT id, item_name, item_code, unit, unit_price, total_price, "
                    "quantity, project_name, project_type, year, region, brand, origin, "
                    "material_spec, embedding, source_file, created_at, status "
                    "FROM price_records WHERE status = ? AND embedding IS NOT NULL",
                    (status,),
                )
                rows = cursor.fetchall()
                if not rows:
                    return []

                query_vec = np.array(query_embedding, dtype=np.float32)
                query_norm = np.linalg.norm(query_vec)
                if query_norm == 0:
                    return []
                query_vec = query_vec / query_norm

                scored = []
                for row in rows:
                    db_vec = _blob_to_vector(row["embedding"])
                    db_norm = np.linalg.norm(db_vec)
                    if db_norm == 0:
                        continue
                    similarity = float(np.dot(query_vec, db_vec / db_norm))
                    scored.append((similarity, row))

                scored.sort(key=lambda x: x[0], reverse=True)
                candidate_rows = scored[:top_k]
            else:
                if self.has_pgvector:
                    with conn.cursor() as cur:
                        # pgvector cosine distance operator is <=>
                        # similarity = 1.0 - distance
                        query_str = _vector_to_postgres(query_embedding)
                        cur.execute(
                            """
                            SELECT id, item_name, item_code, unit, unit_price, total_price,
                                   quantity, project_name, project_type, year, region, brand, origin,
                                   material_spec, source_file, created_at, status,
                                   (embedding <=> %s::vector) AS distance
                            FROM price_records
                            WHERE status = %s AND embedding IS NOT NULL
                            ORDER BY embedding <=> %s::vector ASC
                            LIMIT %s
                            """,
                            (query_str, status, query_str, top_k),
                        )
                        db_rows = cur.fetchall()
                        candidate_rows = []
                        for row in db_rows:
                            distance = row["distance"]
                            similarity = 1.0 - float(distance) if distance is not None else 0.0
                            candidate_rows.append((similarity, row))
                else:
                    # Fetch all with embeddings and compute cosine similarity in Python
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT id, item_name, item_code, unit, unit_price, total_price,
                                   quantity, project_name, project_type, year, region, brand, origin,
                                   material_spec, source_file, created_at, status, embedding
                            FROM price_records
                            WHERE status = %s AND embedding IS NOT NULL
                            """,
                            (status,),
                        )
                        rows = cur.fetchall()
                    if not rows:
                        return []

                    query_vec = np.array(query_embedding, dtype=np.float32)
                    query_norm = np.linalg.norm(query_vec)
                    if query_norm == 0:
                        return []
                    query_vec = query_vec / query_norm

                    scored = []
                    for row in rows:
                        db_vec = np.array(row["embedding"], dtype=np.float32)
                        db_norm = np.linalg.norm(db_vec)
                        if db_norm == 0:
                            continue
                        similarity = float(np.dot(query_vec, db_vec / db_norm))
                        scored.append((similarity, row))

                    scored.sort(key=lambda x: x[0], reverse=True)
                    candidate_rows = scored[:top_k]

        vocabulary = self._bidder_vocabulary()
        results: list[SimilarItem] = []
        for similarity, row in candidate_rows:
            brand_name, bidder_name = split_brand_bidder(row["brand"], vocabulary)
            record = PriceRecord(
                id=row["id"],
                item_name=row["item_name"],
                item_code=row["item_code"],
                unit=row["unit"],
                unit_price=row["unit_price"],
                total_price=row["total_price"],
                quantity=row["quantity"],
                project_name=row["project_name"],
                project_type=row["project_type"],
                year=row["year"],
                region=row["region"],
                brand=brand_name or row["brand"],
                bidder=bidder_name,
                origin=row["origin"],
                material_spec=row["material_spec"],
                source_file=row["source_file"],
                created_at=str(row["created_at"]),
                status=row["status"],
            )
            results.append(SimilarItem(record=record, similarity_score=similarity))
        return results

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics about the price database."""
        conn = self._conn()

        if self._provider == "sqlite":
            total = conn.execute("SELECT COUNT(*) FROM price_records WHERE status = 'active'").fetchone()[0]
            with_embedding = conn.execute(
                "SELECT COUNT(*) FROM price_records WHERE status = 'active' AND embedding IS NOT NULL"
            ).fetchone()[0]
            year_range = conn.execute(
                "SELECT MIN(year), MAX(year) FROM price_records WHERE status = 'active' AND year IS NOT NULL"
            ).fetchone()
            project_count = conn.execute(
                "SELECT COUNT(DISTINCT project_name) FROM price_records WHERE status = 'active'"
            ).fetchone()[0]
            feedback_count = conn.execute("SELECT COUNT(*) FROM feedback_log").fetchone()[0]
            db_info = str(self._path)
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM price_records WHERE status = 'active'")
                total = cur.fetchone()["count"] or 0

                cur.execute("SELECT COUNT(*) FROM price_records WHERE status = 'active' AND embedding IS NOT NULL")
                with_embedding = cur.fetchone()["count"] or 0

                cur.execute("SELECT MIN(year), MAX(year) FROM price_records WHERE status = 'active' AND year IS NOT NULL")
                year_range_row = cur.fetchone()
                year_range = (year_range_row["min"], year_range_row["max"]) if year_range_row else (None, None)

                cur.execute("SELECT COUNT(DISTINCT project_name) FROM price_records WHERE status = 'active'")
                project_count = cur.fetchone()["count"] or 0

                cur.execute("SELECT COUNT(*) FROM feedback_log")
                feedback_count = cur.fetchone()["count"] or 0

            db_info = f"PostgreSQL tại {self._config.db_host}:{self._config.db_port}/{self._config.db_name}"

        return {
            "total_records": total,
            "records_with_embedding": with_embedding,
            "year_min": year_range[0] if year_range else None,
            "year_max": year_range[1] if year_range else None,
            "project_count": project_count,
            "feedback_entries": feedback_count,
            "db_path": db_info,
        }

    def close(self) -> None:
        if hasattr(self._local, "sqlite_conn") and self._local.sqlite_conn:
            self._local.sqlite_conn.close()
            self._local.sqlite_conn = None
        if hasattr(self._local, "postgres_conn") and self._local.postgres_conn:
            self._local.postgres_conn.close()
            self._local.postgres_conn = None
