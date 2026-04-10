"""
DuckDB 存储适配器
=================
三层数据架构：
  Layer 1: raw_profiles, raw_behaviors  — 原始数据（从 txt 加载）
  Layer 2: semantic_events              — 语义事件流（CEP 清洗产出，EAV 结构）
           feature_wide_view            — 动态宽表（PIVOT 视图，自动跟随 CEP 变更）
  Layer 3: need_tags                    — NEED 打标结果（user_id, need_label, confidence）
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore

try:
    import pyarrow as pa
except ImportError:
    pa = None  # type: ignore

from neotrace.storage.base import StorageAdapter


class DuckDBAdapter(StorageAdapter):

    def __init__(self, db_path: str = ":memory:"):
        if duckdb is None:
            raise ImportError("duckdb 未安装，请运行: pip install duckdb pyarrow")
        self._con = duckdb.connect(db_path)
        self._init_schema()

    # ── Schema 初始化 ─────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS raw_profiles (
                user_id      VARCHAR PRIMARY KEY,
                data         JSON,
                is_converted INTEGER DEFAULT 0,
                split        VARCHAR DEFAULT 'train'  -- 'train' | 'val'
            )
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS raw_behaviors (
                id          VARCHAR DEFAULT gen_random_uuid(),
                user_id     VARCHAR NOT NULL,
                event_raw   VARCHAR,       -- 原始行为描述
                event_time  TIMESTAMP,
                extra       JSON
            )
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS semantic_events (
                id          VARCHAR DEFAULT gen_random_uuid(),
                user_id     VARCHAR NOT NULL,
                event_type  VARCHAR NOT NULL,  -- 语义化事件类型，如 frequent_app_browse
                event_time  TIMESTAMP,
                properties  JSON               -- 附加属性
            )
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                rule_id     VARCHAR PRIMARY KEY,
                rule_type   VARCHAR NOT NULL,  -- cep_clean | need_segment
                name        VARCHAR,
                description VARCHAR,
                conditions  JSON,              -- 规则条件列表
                need_label  VARCHAR,           -- NEED 规则专用
                status      VARCHAR DEFAULT 'draft',  -- draft|validated|published|rejected
                tgi         DOUBLE,
                support     DOUBLE,
                hit_users   INTEGER,
                created_at  TIMESTAMP DEFAULT now(),
                updated_at  TIMESTAMP DEFAULT now()
            )
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS need_tags (
                user_id     VARCHAR NOT NULL,
                need_label  VARCHAR NOT NULL,
                confidence  DOUBLE DEFAULT 1.0,
                PRIMARY KEY (user_id, need_label)
            )
        """)

    # ── 原始数据加载 ──────────────────────────────────────────────────────────

    def load_raw_profiles(self, path: str, val_ratio: float = 0.0,
                          force_converted: int | None = None) -> int:
        """
        从 txt 文件加载用户画像。
        val_ratio:       验证集比例（0.0 表示全部划为训练集）。
                         分层抽样：正样本和负样本各按 val_ratio 随机抽取进验证集，
                         保证两个 split 的正负比例一致。
        force_converted: 若不为 None，强制覆盖所有行的 is_converted 值（1=正样本文件，0=负样本文件）。
        """
        import random
        p = Path(path)
        content = p.read_text(encoding="utf-8").strip()
        lines = content.splitlines()

        rows = self._parse_txt(lines)

        # 分层抽样：先按 is_converted 分组
        pos_rows, neg_rows = [], []
        parsed = []
        for row in rows:
            user_id = row.get("user_id") or row.get("uid") or str(uuid.uuid4())
            profile_data = self._expand_user_tag(row)
            if force_converted is not None:
                is_converted = force_converted
            else:
                is_converted = int(row.get("is_converted", row.get("converted", 0)))
                if not is_converted and "user_events" in row:
                    is_converted = self._infer_converted_from_events(row["user_events"])
            parsed.append((user_id, profile_data, is_converted))
            (pos_rows if is_converted else neg_rows).append(len(parsed) - 1)

        # 随机打乱后按比例切分（分别对正负样本切）
        if val_ratio > 0:
            random.shuffle(pos_rows)
            random.shuffle(neg_rows)
            pos_val_n = max(1, int(len(pos_rows) * val_ratio))
            neg_val_n = max(1, int(len(neg_rows) * val_ratio))
            val_indices = set(pos_rows[:pos_val_n] + neg_rows[:neg_val_n])
        else:
            val_indices = set()

        count = 0
        for idx, (user_id, profile_data, is_converted) in enumerate(parsed):
            split = "val" if idx in val_indices else "train"
            self._con.execute(
                "INSERT OR REPLACE INTO raw_profiles VALUES (?, ?, ?, ?)",
                [user_id, json.dumps(profile_data, ensure_ascii=False), is_converted, split]
            )
            count += 1
        return count

    def load_raw_behaviors(self, path: str) -> int:
        """
        从 txt 文件加载用户行为数据。
        支持格式：
          1. 每行一个行为 JSON（含 user_id, event 字段）
          2. 合并格式：含 user_events 列表的完整记录，自动展开每条事件
        """
        p = Path(path)
        content = p.read_text(encoding="utf-8").strip()
        lines = content.splitlines()

        rows = self._parse_txt(lines)
        count = 0
        for row in rows:
            user_id = row.get("user_id") or row.get("uid", "unknown")
            # 合并格式：user_events 是事件列表
            if "user_events" in row:
                for evt in row["user_events"]:
                    event_raw = evt.get("res_key") or evt.get("event") or ""
                    event_time = self._parse_event_time(evt)
                    self._con.execute(
                        "INSERT INTO raw_behaviors(user_id, event_raw, event_time, extra) VALUES (?,?,?,?)",
                        [user_id, event_raw, event_time, json.dumps(evt, ensure_ascii=False)]
                    )
                    count += 1
            else:
                event_raw = row.get("event") or row.get("action") or json.dumps(row)
                event_time = row.get("event_time") or row.get("time")
                self._con.execute(
                    "INSERT INTO raw_behaviors(user_id, event_raw, event_time, extra) VALUES (?,?,?,?)",
                    [user_id, event_raw, event_time, json.dumps(row, ensure_ascii=False)]
                )
                count += 1
        return count

    @staticmethod
    def _expand_user_tag(row: dict) -> dict:
        """
        展开 user_tag 字段（key:value#key:value 格式）到独立字段。
        同时保留原始 user_tag 字符串，去除 user_events 大列表。
        """
        result = {k: v for k, v in row.items() if k not in ("user_events",)}
        tag_str = row.get("user_tag", "")
        if tag_str:
            for pair in tag_str.split("#"):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    result[k.strip()] = v.strip()
        return result

    @staticmethod
    def _infer_converted_from_events(events: list) -> int:
        """从 user_events 列表推断是否有留资事件"""
        for evt in events:
            res_key = evt.get("res_key") or evt.get("event") or ""
            if res_key.startswith("留资_"):
                return 1
        return 0

    def _parse_txt(self, lines: list[str]) -> list[dict]:
        """自动识别 JSON-lines 或 TSV 格式"""
        if not lines:
            return []
        # 尝试 JSON-lines
        try:
            return [json.loads(l) for l in lines if l.strip()]
        except json.JSONDecodeError:
            pass
        # 尝试 TSV
        headers = lines[0].split("\t")
        result = []
        for line in lines[1:]:
            if line.strip():
                vals = line.split("\t")
                result.append(dict(zip(headers, vals)))
        return result

    @staticmethod
    def _parse_event_time(evt: dict) -> str | None:
        """
        将事件里各种时间格式统一转为 'YYYY-MM-DD HH:MM:SS'。
        支持：
          timestamp: "2025120516"  → YYYYMMDDH[H] → "2025-12-05 16:00:00"
          time_str:  "20251205"    → YYYYMMDD      → "2025-12-05 00:00:00"
          event_time: "2026-01-05 10:00:00" → 直接返回
        """
        # 优先取标准格式
        et = evt.get("event_time")
        if et and "-" in str(et):
            return et

        # timestamp 字段：纯数字，长度 10=YYYYMMDDHH 或 12=YYYYMMDDHHMI
        ts = str(evt.get("timestamp") or "").strip()
        if ts.isdigit():
            if len(ts) >= 10:
                return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:00:00"
            if len(ts) == 8:
                return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} 00:00:00"

        # time_str 字段：YYYYMMDD
        tstr = str(evt.get("time_str") or "").strip()
        if tstr.isdigit() and len(tstr) == 8:
            return f"{tstr[:4]}-{tstr[4:6]}-{tstr[6:8]} 00:00:00"

        return None

    # ── Schema 信息 ───────────────────────────────────────────────────────────

    def get_profile_schema(self) -> dict[str, str]:
        """从 raw_profiles 的 JSON data 中采样提取字段及类型"""
        rows = self._con.execute(
            "SELECT data FROM raw_profiles LIMIT 100"
        ).fetchall()
        fields: dict[str, str] = {}
        for (data,) in rows:
            obj = json.loads(data) if isinstance(data, str) else data
            for k, v in obj.items():
                if k not in fields:
                    fields[k] = type(v).__name__
        return fields

    def get_behavior_schema(self) -> dict[str, str]:
        """从 raw_behaviors 采样提取字段"""
        rows = self._con.execute(
            "SELECT extra FROM raw_behaviors LIMIT 100"
        ).fetchall()
        fields: dict[str, str] = {}
        for (extra,) in rows:
            obj = json.loads(extra) if isinstance(extra, str) else (extra or {})
            for k, v in obj.items():
                if k not in fields:
                    fields[k] = type(v).__name__
        return fields

    def get_field_distribution(self, table: str, field: str) -> list[dict]:
        """返回指定字段的值分布（Top 50）"""
        if table == "profiles":
            sql = f"""
                SELECT json_extract_string(data, '$.{field}') AS value,
                       count(*) AS cnt,
                       round(count(*) * 100.0 / (SELECT count(*) FROM raw_profiles), 2) AS pct
                FROM raw_profiles
                GROUP BY 1 ORDER BY cnt DESC LIMIT 50
            """
        else:
            sql = f"""
                SELECT json_extract_string(extra, '$.{field}') AS value,
                       count(*) AS cnt,
                       round(count(*) * 100.0 / (SELECT count(*) FROM raw_behaviors), 2) AS pct
                FROM raw_behaviors
                GROUP BY 1 ORDER BY cnt DESC LIMIT 50
            """
        rows = self._con.execute(sql).fetchall()
        return [{"value": r[0], "count": r[1], "pct": r[2]} for r in rows]

    def get_conversion_rate(self, split: str | None = None) -> float:
        """全样本或指定 split 的留资率"""
        where = f"WHERE split = '{split}'" if split else ""
        row = self._con.execute(
            f"SELECT avg(is_converted) FROM raw_profiles {where}"
        ).fetchone()
        return float(row[0] or 0.0)

    def get_split_stats(self) -> dict:
        """返回训练集/验证集的用户数和正样本比例"""
        rows = self._con.execute("""
            SELECT split,
                   count(*) AS total,
                   sum(is_converted) AS pos,
                   avg(CAST(is_converted AS DOUBLE)) AS pos_rate
            FROM raw_profiles
            GROUP BY split ORDER BY split
        """).fetchall()
        return {r[0]: {"total": r[1], "pos": r[2], "pos_rate": round(r[3], 4)} for r in rows}

    # ── 语义事件流 ────────────────────────────────────────────────────────────

    def insert_semantic_events(self, events: list[dict]) -> None:
        for e in events:
            self._con.execute(
                "INSERT INTO semantic_events(user_id, event_type, event_time, properties) VALUES (?,?,?,?)",
                [e["user_id"], e["event_type"], e.get("event_time"), json.dumps(e.get("properties", {}))]
            )

    def rebuild_feature_wide_table(self) -> None:
        """
        从语义事件流动态 PIVOT 重建宽表物化表。
        DuckDB 不支持在 VIEW 里动态推断 PIVOT 列，因此改为
        每次 rebuild 时 DROP + CREATE TABLE AS SELECT，
        新增 event_type 自动出现为新列，无需手写 DDL。
        """
        self._con.execute("DROP TABLE IF EXISTS feature_wide_view")
        self._con.execute("""
            CREATE TABLE feature_wide_view AS
            PIVOT (
                SELECT se.user_id,
                       se.event_type,
                       rp.is_converted,
                       rp.data AS profile_json
                FROM semantic_events se
                JOIN raw_profiles rp ON se.user_id = rp.user_id
            )
            ON event_type
            USING count(*) > 0
            GROUP BY user_id, is_converted, profile_json
        """)

    def get_feature_table(self) -> pa.Table:
        """返回宽表 Arrow Table"""
        return self._con.execute("SELECT * FROM feature_wide_view").arrow()

    # ── 规则存储 ──────────────────────────────────────────────────────────────

    def save_rule(self, rule: dict) -> str:
        rule_id = rule.get("rule_id") or str(uuid.uuid4())
        self._con.execute(
            """INSERT OR REPLACE INTO rules
               (rule_id, rule_type, name, description, conditions, need_label, status, tgi, support, hit_users)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                rule_id,
                rule.get("rule_type", "cep_clean"),
                rule.get("name", ""),
                rule.get("description", ""),
                json.dumps(rule.get("conditions", []), ensure_ascii=False),
                rule.get("need_label"),
                rule.get("status", "draft"),
                rule.get("tgi"),
                rule.get("support"),
                rule.get("hit_users"),
            ]
        )
        return rule_id

    def get_rules(self, status: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT * FROM rules WHERE status = ? ORDER BY created_at", [status]
        ).fetchall()
        cols = [d[0] for d in self._con.description]
        return [dict(zip(cols, r)) for r in rows]

    def update_rule_status(self, rule_id: str, status: str, metrics: dict | None = None) -> None:
        if metrics:
            self._con.execute(
                """UPDATE rules SET status=?, tgi=?, support=?, hit_users=?, updated_at=now()
                   WHERE rule_id=?""",
                [status, metrics.get("tgi"), metrics.get("support"), metrics.get("hit_users"), rule_id]
            )
        else:
            # 只更新状态，不覆盖已有 metrics
            self._con.execute(
                "UPDATE rules SET status=?, updated_at=now() WHERE rule_id=?",
                [status, rule_id]
            )

    # ── TGI 计算 ──────────────────────────────────────────────────────────────

    def compute_tgi(self, sql_condition: str, split: str | None = None) -> dict:
        """
        计算规则命中用户的 TGI。
        split: 'train' | 'val' | None（None 表示全量）
        """
        split_filter = f"AND rp.split = '{split}'" if split else ""
        split_filter_wide = f"AND split = '{split}'" if split else ""

        total_sql = f"SELECT count(*), avg(CAST(is_converted AS DOUBLE)) FROM raw_profiles WHERE 1=1 {split_filter.replace('AND rp.', 'AND ')}"
        total_row = self._con.execute(total_sql).fetchone()
        total = total_row[0] or 0
        global_rate = float(total_row[1] or 0.0)

        if global_rate == 0 or total == 0:
            return {"tgi": 0, "support": 0, "hit_users": 0,
                    "hit_conversion_rate": 0, "global_conversion_rate": 0}

        wide_table_exists = self._con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='feature_wide_view'"
        ).fetchone()[0] > 0

        try:
            if wide_table_exists and "rp." not in sql_condition and "rb." not in sql_condition:
                row = self._con.execute(f"""
                    SELECT count(*) AS hit_users,
                           avg(CAST(is_converted AS DOUBLE)) AS hit_cvr
                    FROM feature_wide_view
                    WHERE {sql_condition} {split_filter_wide}
                """).fetchone()
            else:
                row = self._con.execute(f"""
                    SELECT count(DISTINCT rp.user_id) AS hit_users,
                           avg(CAST(rp.is_converted AS DOUBLE)) AS hit_cvr
                    FROM raw_profiles rp
                    LEFT JOIN raw_behaviors rb ON rp.user_id = rb.user_id
                    WHERE {sql_condition} {split_filter}
                """).fetchone()
        except Exception as e:
            return {"tgi": 0, "support": 0, "hit_users": 0,
                    "hit_conversion_rate": 0, "global_conversion_rate": 0,
                    "error": str(e)}

        hit_users = row[0] or 0
        hit_cvr = float(row[1] or 0.0)
        support = round(hit_users / total, 4) if total else 0
        tgi = round((hit_cvr / global_rate) * 100, 1) if global_rate else 0

        return {
            "hit_users": hit_users,
            "hit_conversion_rate": round(hit_cvr, 4),
            "global_conversion_rate": round(global_rate, 4),
            "tgi": tgi,
            "support": support,
        }

    # ── 便捷方法 ──────────────────────────────────────────────────────────────

    def query(self, sql: str) -> list[dict]:
        """执行任意 SQL，返回结果列表"""
        rows = self._con.execute(sql).fetchall()
        cols = [d[0] for d in self._con.description]
        return [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        self._con.close()
