#!/usr/bin/env python3
"""
rule_expr.py — Need/CEP 规则表达式解析器 & 执行器
===================================================

支持两类规则，共用同一解析器：

━━━ Need 圈选规则（基于 user_derived_events + user_profile）━━━

  event.<event_type>.exists               -- 有该衍生事件
  event.<event_type>.count >= N           -- 衍生事件次数（>= <= > < = !=）
  event.<event_type>.days_since <= N      -- 距今天数

  profile.<field> = "value"              -- 画像精确匹配
  profile.<field> != "value"
  profile.<field> >= N / <= N / > N / < N
  profile.<field> IN ["v1","v2",...]
  profile.<field> NOT IN [...]

━━━ CEP 规则（基于 user_raw_events）━━━

  raw.<event_type>.exists                             -- 有该原始事件
  raw.<event_type>.count >= N                         -- 原始事件次数
  raw.<event_type>.days >= N                          -- 跨越不同日期数（distinct time_str）
  raw.<event_type>.dur_max >= N                       -- 最大停留秒数
  raw.<event_type>[<attr>!=null].count >= N           -- 属性非空过滤后计数
  raw.<event_type>[<attr>=<val>].count >= N           -- 属性等值过滤后计数
  raw.<event_type>[<attr>].distinct >= N              -- 属性去重计数（如 distinct brand）
  raw.<event_type>.contains("keyword")                -- attr_json 任意字段含该关键词（LIKE）
  raw.<A>.before.<B>.exists                           -- A 在时间上先于 B（时序）
  raw.<A>[<attr>].same.raw.<B>[<attr>].exists         -- 两事件有至少一个相同属性值

━━━ 逻辑组合（两类规则均支持）━━━
  AND / OR / NOT (...)                    -- 优先级：NOT > AND > OR

━━━ 示例 ━━━
  # Need 规则
  event.view_loan_calc.exists AND event.view_car_detail.count >= 1
  profile.city_tier IN ["一线","新一线"] AND NOT profile.car_status = "有车"

  # CEP 规则
  raw.search_vertical[brand!=null].count >= 3
  raw.search_vertical[brand].distinct >= 3
  raw.view_car_detail.before.view_loan_calc.exists
  raw.view_car_detail[brand].same.raw.view_loan_calc[brand].exists
  raw.search_vertical.days >= 3 AND raw.search_vertical.count >= 5
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Token 类型常量
# ─────────────────────────────────────────────────────────────────────────────

_TT_AND     = "AND"
_TT_OR      = "OR"
_TT_NOT     = "NOT"
_TT_LPAREN  = "LPAREN"
_TT_RPAREN  = "RPAREN"
_TT_EVENT   = "EVENT"    # event.<type>.<attr>
_TT_PROFILE = "PROFILE"  # profile.<field>
_TT_RAW     = "RAW"      # raw.* 系列（解析后直接生成 RawCondNode）
_TT_OP      = "OP"       # >= <= > < = !=
_TT_IN      = "IN"
_TT_NOT_IN  = "NOT_IN"
_TT_NUMBER  = "NUMBER"
_TT_STRING  = "STRING"
_TT_LBRACK  = "LBRACK"
_TT_RBRACK  = "RBRACK"
_TT_COMMA   = "COMMA"
_TT_EOF     = "EOF"


class Token:
    def __init__(self, type_: str, value: Any):
        self.type  = type_
        self.value = value

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────────────────────────────────────

def tokenize(expr: str) -> list[Token]:
    """将表达式字符串拆分为 Token 列表"""
    tokens: list[Token] = []
    i = 0
    text = expr.strip()
    n = len(text)

    while i < n:
        # 跳过空白和换行
        if text[i].isspace():
            i += 1
            continue

        # 括号
        if text[i] == "(":
            tokens.append(Token(_TT_LPAREN, "("))
            i += 1
            continue
        if text[i] == ")":
            tokens.append(Token(_TT_RPAREN, ")"))
            i += 1
            continue

        # 方括号（属性过滤 / IN 列表）
        if text[i] == "[":
            tokens.append(Token(_TT_LBRACK, "["))
            i += 1
            continue
        if text[i] == "]":
            tokens.append(Token(_TT_RBRACK, "]"))
            i += 1
            continue

        # 逗号
        if text[i] == ",":
            tokens.append(Token(_TT_COMMA, ","))
            i += 1
            continue

        # 运算符（双字符优先）
        if text[i:i+2] in (">=", "<=", "!="):
            tokens.append(Token(_TT_OP, text[i:i+2]))
            i += 2
            continue
        if text[i] in (">", "<", "="):
            tokens.append(Token(_TT_OP, text[i]))
            i += 1
            continue

        # 字符串字面量（单引号或双引号）
        if text[i] in ('"', "'"):
            quote = text[i]
            j = i + 1
            while j < n and text[j] != quote:
                j += 1
            tokens.append(Token(_TT_STRING, text[i+1:j]))
            i = j + 1
            continue

        # 数字（含负数、小数）
        if text[i].isdigit() or (text[i] == "-" and i+1 < n and text[i+1].isdigit()):
            j = i + 1
            while j < n and (text[j].isdigit() or text[j] == "."):
                j += 1
            tokens.append(Token(_TT_NUMBER, float(text[i:j])))
            i = j
            continue

        # 标识符：关键字 / event.* / profile.* / raw.*
        if text[i].isalpha() or text[i] == "_":
            j = i
            # raw.* 包含可选的 [attr_filter] 和 .before./.same. 等复合结构
            # 先贪婪读取 word 部分（只到 [、空白或运算符）
            while j < n and (text[j].isalnum() or text[j] in ("_", ".")):
                j += 1
            word = text[i:j]
            upper = word.upper()

            if upper == "AND":
                tokens.append(Token(_TT_AND, "AND"))
            elif upper == "OR":
                tokens.append(Token(_TT_OR, "OR"))
            elif upper == "NOT":
                rest = text[j:].lstrip()
                if rest.upper().startswith("IN"):
                    skip = len(text[j:]) - len(rest) + 2
                    tokens.append(Token(_TT_NOT_IN, "NOT IN"))
                    j += skip
                else:
                    tokens.append(Token(_TT_NOT, "NOT"))
            elif upper == "IN":
                tokens.append(Token(_TT_IN, "IN"))
            elif word.startswith("raw."):
                # raw.* 系列：完整解析（含可选 [filter] 和复合动词）
                # 把 j 之后可能出现的 [filter] 也吃进来
                tok, j = _tokenize_raw(text, i, n)
                tokens.append(tok)
            elif word.startswith("event."):
                parts = word.split(".", 2)
                if len(parts) != 3:
                    raise SyntaxError(f"event 引用格式应为 event.<type>.<attr>，实际: {word!r}")
                tokens.append(Token(_TT_EVENT, {"event_type": parts[1], "attr": parts[2]}))
            elif word.startswith("profile."):
                parts = word.split(".", 1)
                tokens.append(Token(_TT_PROFILE, {"field": parts[1]}))
            else:
                raise SyntaxError(f"无法识别的标识符: {word!r}")
            i = j
            continue

        raise SyntaxError(f"无法识别的字符: {text[i]!r} (位置 {i})")

    tokens.append(Token(_TT_EOF, None))
    return tokens


def _tokenize_raw(text: str, start: int, n: int) -> tuple[Token, int]:
    """
    从 start 位置解析完整的 raw.* token。
    raw. 后紧跟 event_type（到下一个 . 为止），然后是可选 [filter]，然后是动词段。
    """
    i = start

    def read_word(pos: int) -> tuple[str, int]:
        """读取单个 word（字母/数字/下划线，不含 .）"""
        j = pos
        while j < n and (text[j].isalnum() or text[j] == "_"):
            j += 1
        return text[pos:j], j

    def read_bracket_filter(pos: int) -> tuple[dict | None, int]:
        if pos >= n or text[pos] != "[":
            return None, pos
        end = text.index("]", pos + 1)
        inner = text[pos+1:end].strip()
        result_pos = end + 1
        for op in ("!=", ">=", "<=", "=", ">", "<"):
            if op in inner:
                parts = inner.split(op, 1)
                attr = parts[0].strip()
                val  = parts[1].strip().strip('"').strip("'")
                if val.lower() == "null":
                    val = None
                return {"attr": attr, "op": op, "val": val, "mode": "filter"}, result_pos
        # 只有属性名 → distinct 模式
        return {"attr": inner.strip(), "op": None, "val": None, "mode": "distinct"}, result_pos

    def expect_dot(pos: int) -> int:
        if pos >= n or text[pos] != ".":
            raise SyntaxError(f"raw 表达式位置 {pos} 期望 '.'，实际 {text[pos:pos+5]!r}")
        return pos + 1

    # 跳过 "raw."
    i += len("raw.")

    # 读 event_A
    event_a, i = read_word(i)
    if not event_a:
        raise SyntaxError("raw. 后缺少事件名")

    # 可选属性过滤 A
    filter_a, i = read_bracket_filter(i)

    # 读 "."
    i = expect_dot(i)

    # 读动词（单词，不含 .）
    verb, i = read_word(i)

    if verb == "exists":
        return Token(_TT_RAW, {
            "kind": "single", "event": event_a, "filter": filter_a,
            "attr": "exists", "op": None, "value": None,
        }), i

    if verb in ("count", "days", "dur_max", "distinct"):
        return Token(_TT_RAW, {
            "kind": "single", "event": event_a, "filter": filter_a,
            "attr": verb, "op": None, "value": None,
        }), i

    if verb == "contains":
        # raw.<event>.contains("keyword") — attr_json 任意字段含该关键词
        # 跳过可选空白，读 ( "keyword" )
        while i < n and text[i].isspace():
            i += 1
        if i >= n or text[i] != "(":
            raise SyntaxError(f"raw.{event_a}.contains 后期望 (\"keyword\")")
        i += 1  # skip (
        while i < n and text[i].isspace():
            i += 1
        if i >= n or text[i] not in ('"', "'"):
            raise SyntaxError(f"raw.{event_a}.contains 括号内期望字符串")
        quote = text[i]; i += 1
        j = i
        while j < n and text[j] != quote:
            j += 1
        keyword = text[i:j]; i = j + 1
        while i < n and text[i].isspace():
            i += 1
        if i >= n or text[i] != ")":
            raise SyntaxError(f"raw.{event_a}.contains 缺少闭合括号")
        i += 1  # skip )
        return Token(_TT_RAW, {
            "kind": "single", "event": event_a, "filter": filter_a,
            "attr": "contains", "op": None, "value": keyword,
        }), i

    if verb == "before":
        # raw.<A>.before.<B>.exists
        i = expect_dot(i)
        event_b, i = read_word(i)
        if not event_b:
            raise SyntaxError("before 后缺少事件名 B")
        i = expect_dot(i)
        final, i = read_word(i)
        if final != "exists":
            raise SyntaxError(f"raw.A.before.B 后应跟 .exists，实际: {final!r}")
        return Token(_TT_RAW, {
            "kind": "before",
            "event_a": event_a, "filter_a": filter_a,
            "event_b": event_b, "filter_b": None,
        }), i

    if verb == "same":
        # raw.<A>[attr].same.raw.<B>[attr].exists
        i = expect_dot(i)
        # 读 "raw"
        raw_kw, i = read_word(i)
        if raw_kw != "raw":
            raise SyntaxError(f"same 后应跟 raw.<B>，实际: {raw_kw!r}")
        i = expect_dot(i)
        event_b, i = read_word(i)
        if not event_b:
            raise SyntaxError("same.raw. 后缺少事件名 B")
        filter_b, i = read_bracket_filter(i)
        i = expect_dot(i)
        final, i = read_word(i)
        if final != "exists":
            raise SyntaxError(f"raw.A.same.raw.B 后应跟 .exists，实际: {final!r}")
        return Token(_TT_RAW, {
            "kind": "same_attr",
            "event_a": event_a, "filter_a": filter_a,
            "event_b": event_b, "filter_b": filter_b,
        }), i

    raise SyntaxError(
        f"raw.{event_a} 后的动词 {verb!r} 不支持，"
        f"可用: exists / count / days / dur_max / distinct / contains / before / same"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AST 节点
# ─────────────────────────────────────────────────────────────────────────────

class ASTNode:
    pass


class AndNode(ASTNode):
    def __init__(self, left: ASTNode, right: ASTNode):
        self.left  = left
        self.right = right


class OrNode(ASTNode):
    def __init__(self, left: ASTNode, right: ASTNode):
        self.left  = left
        self.right = right


class NotNode(ASTNode):
    def __init__(self, operand: ASTNode):
        self.operand = operand


class EventCondNode(ASTNode):
    """event.<event_type>.<attr> [op value]"""
    def __init__(self, event_type: str, attr: str, op: str | None, value: Any):
        self.event_type = event_type
        self.attr       = attr
        self.op         = op
        self.value      = value


class ProfileCondNode(ASTNode):
    """profile.<field> op value"""
    def __init__(self, field: str, op: str, value: Any):
        self.field = field
        self.op    = op
        self.value = value


class RawCondNode(ASTNode):
    """raw.* 系列条件（原始事件）"""
    def __init__(self, raw_token: dict, op: str | None = None, value: Any = None):
        self.raw   = raw_token   # tokenizer 已解析的结构
        self.op    = op
        self.value = value


# ─────────────────────────────────────────────────────────────────────────────
# 递归下降解析器
# ─────────────────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos    = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def consume(self, expected_type: str | None = None) -> Token:
        tok = self.tokens[self.pos]
        if expected_type and tok.type != expected_type:
            raise SyntaxError(f"期望 {expected_type}，实际是 {tok.type}({tok.value!r})")
        self.pos += 1
        return tok

    def parse(self) -> ASTNode:
        node = self._parse_or()
        self.consume(_TT_EOF)
        return node

    def _parse_or(self) -> ASTNode:
        left = self._parse_and()
        while self.peek().type == _TT_OR:
            self.consume(_TT_OR)
            right = self._parse_and()
            left = OrNode(left, right)
        return left

    def _parse_and(self) -> ASTNode:
        left = self._parse_not()
        while self.peek().type == _TT_AND:
            self.consume(_TT_AND)
            right = self._parse_not()
            left = AndNode(left, right)
        return left

    def _parse_not(self) -> ASTNode:
        if self.peek().type == _TT_NOT:
            self.consume(_TT_NOT)
            return NotNode(self._parse_not())
        return self._parse_atom()

    def _parse_atom(self) -> ASTNode:
        tok = self.peek()

        if tok.type == _TT_LPAREN:
            self.consume(_TT_LPAREN)
            node = self._parse_or()
            self.consume(_TT_RPAREN)
            return node

        if tok.type == _TT_EVENT:
            return self._parse_event_cond()

        if tok.type == _TT_PROFILE:
            return self._parse_profile_cond()

        if tok.type == _TT_RAW:
            return self._parse_raw_cond()

        raise SyntaxError(f"期望条件表达式，实际是 {tok.type}({tok.value!r})")

    def _parse_event_cond(self) -> EventCondNode:
        tok        = self.consume(_TT_EVENT)
        event_type = tok.value["event_type"]
        attr       = tok.value["attr"]

        if attr == "exists":
            return EventCondNode(event_type, "exists", None, None)
        if attr in ("count", "days_since"):
            op  = self.consume(_TT_OP).value
            val = self.consume(_TT_NUMBER).value
            return EventCondNode(event_type, attr, op, val)
        raise SyntaxError(f"event 属性 {attr!r} 不支持，可用: exists / count / days_since")

    def _parse_profile_cond(self) -> ProfileCondNode:
        tok   = self.consume(_TT_PROFILE)
        field = tok.value["field"]
        next_ = self.peek()

        if next_.type in (_TT_IN, _TT_NOT_IN):
            op = self.consume().value
            self.consume(_TT_LBRACK)
            values = []
            while self.peek().type != _TT_RBRACK:
                v = self.consume()
                if v.type not in (_TT_STRING, _TT_NUMBER):
                    raise SyntaxError(f"IN 列表中期望字符串或数字，实际 {v.type}")
                values.append(v.value)
                if self.peek().type == _TT_COMMA:
                    self.consume(_TT_COMMA)
            self.consume(_TT_RBRACK)
            return ProfileCondNode(field, op, values)

        if next_.type == _TT_OP:
            op  = self.consume(_TT_OP).value
            val = self.consume()
            if val.type not in (_TT_STRING, _TT_NUMBER):
                raise SyntaxError(f"期望字符串或数字，实际 {val.type}")
            return ProfileCondNode(field, op, val.value)

        raise SyntaxError(f"profile.{field!r} 后期望操作符或 IN")

    def _parse_raw_cond(self) -> RawCondNode:
        tok     = self.consume(_TT_RAW)
        raw_val = tok.value

        # exists / before / same_attr / contains 不需要后续操作符
        if raw_val.get("attr") in ("exists", "contains") or raw_val.get("kind") in ("before", "same_attr"):
            return RawCondNode(raw_val, None, None)

        # count / days / dur_max / distinct 后面跟 op number
        op  = self.consume(_TT_OP).value
        val = self.consume(_TT_NUMBER).value
        return RawCondNode(raw_val, op, val)


def parse_expr(expr: str) -> ASTNode:
    tokens = tokenize(expr)
    return Parser(tokens).parse()


# ─────────────────────────────────────────────────────────────────────────────
# 执行器
# ─────────────────────────────────────────────────────────────────────────────

class Executor:
    """
    将 AST 求值为命中用户集合（set[str]）。
    AND → 交集（短路），OR → 并集，NOT → 全集差集。
    """

    def __init__(self, con: sqlite3.Connection):
        self.con   = con
        self._all: set[str] | None = None

    def _all_users(self) -> set[str]:
        if self._all is None:
            self._all = {r[0] for r in self.con.execute("SELECT user_id FROM user_profile").fetchall()}
        return self._all

    # ── event.* ────────────────────────────────────────────────────────────

    def _eval_event(self, node: EventCondNode) -> set[str]:
        now = datetime.now()
        et  = node.event_type

        if node.attr == "exists":
            return {r[0] for r in self.con.execute(
                "SELECT DISTINCT user_id FROM user_derived_events WHERE derived_event_type=?", (et,)
            ).fetchall()}

        if node.attr == "count":
            return {r[0] for r in self.con.execute(f"""
                SELECT user_id FROM user_derived_events WHERE derived_event_type=?
                GROUP BY user_id HAVING COUNT(*) {node.op} ?
            """, (et, int(node.value))).fetchall()}

        if node.attr == "days_since":
            rows = self.con.execute(
                "SELECT user_id, MAX(event_time) FROM user_derived_events WHERE derived_event_type=? GROUP BY user_id",
                (et,)
            ).fetchall()
            result: set[str] = set()
            thr = float(node.value)
            for uid, ts in rows:
                try:
                    days = (now - datetime.strptime(ts[:8], "%Y%m%d")).days
                except Exception:
                    days = 999
                if _cmp(days, node.op, thr):
                    result.add(uid)
            return result

        raise ValueError(f"未知 event 属性: {node.attr!r}")

    # ── profile.* ──────────────────────────────────────────────────────────

    def _eval_profile(self, node: ProfileCondNode) -> set[str]:
        field, op, val = node.field, node.op, node.value
        if op in ("IN", "NOT IN"):
            ph  = ",".join("?" * len(val))
            sql = f"SELECT user_id FROM user_profile WHERE {field} {'IN' if op=='IN' else 'NOT IN'} ({ph})"
            return {r[0] for r in self.con.execute(sql, val).fetchall()}
        return {r[0] for r in self.con.execute(
            f"SELECT user_id FROM user_profile WHERE {field} {op} ?", (val,)
        ).fetchall()}

    # ── raw.* ──────────────────────────────────────────────────────────────

    def _eval_raw(self, node: RawCondNode) -> set[str]:
        r   = node.raw
        con = self.con

        if r["kind"] == "before":
            # MAX(event_time of A) < MIN(event_time of B) per user
            sql_a = _raw_user_sql(r["event_a"], r.get("filter_a"), "MAX(event_time)")
            sql_b = _raw_user_sql(r["event_b"], r.get("filter_b"), "MIN(event_time)")
            rows = con.execute(f"""
                SELECT a.user_id FROM ({sql_a}) a
                JOIN ({sql_b}) b ON a.user_id=b.user_id
                WHERE a.val < b.val
            """).fetchall()
            return {r[0] for r in rows}

        if r["kind"] == "same_attr":
            # 两事件在同一 attr 字段有相同值
            attr_a = (r.get("filter_a") or {}).get("attr", "brand")
            attr_b = (r.get("filter_b") or {}).get("attr", "brand")
            sql_a  = f"""
                SELECT user_id, json_extract(attr_json,'$.{attr_a}') val
                FROM user_raw_events WHERE event_type=? AND event_type!='lead_submit'
                  AND json_extract(attr_json,'$.{attr_a}') IS NOT NULL
            """
            sql_b  = f"""
                SELECT user_id, json_extract(attr_json,'$.{attr_b}') val
                FROM user_raw_events WHERE event_type=? AND event_type!='lead_submit'
                  AND json_extract(attr_json,'$.{attr_b}') IS NOT NULL
            """
            rows = con.execute(f"""
                SELECT DISTINCT a.user_id FROM ({sql_a}) a
                JOIN ({sql_b}) b ON a.user_id=b.user_id AND a.val=b.val
            """, (r["event_a"], r["event_b"])).fetchall()
            return {row[0] for row in rows}

        # kind == "single"
        event    = r["event"]
        filt     = r.get("filter")
        attr     = r["attr"]
        op, val  = node.op, node.value

        # 构建 WHERE 条件（属性过滤）
        where_extra, params = _build_attr_where(filt)

        if attr == "exists":
            sql = f"""
                SELECT DISTINCT user_id FROM user_raw_events
                WHERE event_type=? AND event_type!='lead_submit'{where_extra}
            """
            return {row[0] for row in con.execute(sql, [event] + params).fetchall()}

        if attr == "contains":
            # attr_json LIKE '%keyword%'（全文匹配整个 JSON 串）
            # keyword = f"%{node.value}%"
            # keyword 存储在 raw["value"] 中，不是 node.value
            keyword = f"%{r.get('value', '')}%"
            sql = f"""
                SELECT DISTINCT user_id FROM user_raw_events
                WHERE event_type=? AND event_type!='lead_submit'
                  AND attr_json LIKE ?{where_extra}
            """
            return {row[0] for row in con.execute(sql, [event, keyword] + params).fetchall()}

        if attr == "count":
            sql = f"""
                SELECT user_id FROM user_raw_events
                WHERE event_type=? AND event_type!='lead_submit'{where_extra}
                GROUP BY user_id HAVING COUNT(*) {op} ?
            """
            return {row[0] for row in con.execute(sql, [event] + params + [int(val)]).fetchall()}

        if attr == "days":
            # 跨越不同日期数（distinct time_str）
            sql = f"""
                SELECT user_id FROM user_raw_events
                WHERE event_type=? AND event_type!='lead_submit'{where_extra}
                GROUP BY user_id HAVING COUNT(DISTINCT time_str) {op} ?
            """
            return {row[0] for row in con.execute(sql, [event] + params + [int(val)]).fetchall()}

        if attr == "dur_max":
            sql = f"""
                SELECT user_id FROM user_raw_events
                WHERE event_type=? AND event_type!='lead_submit'{where_extra}
                GROUP BY user_id HAVING MAX(dur_time) {op} ?
            """
            return {row[0] for row in con.execute(sql, [event] + params + [float(val)]).fetchall()}

        if attr == "distinct":
            # filt.attr 是要 distinct 的字段
            if not filt or not filt.get("attr"):
                raise ValueError("distinct 需要 [attr] 指定去重字段，如 raw.event[brand].distinct >= 3")
            dist_attr = filt["attr"]
            sql = f"""
                SELECT user_id FROM user_raw_events
                WHERE event_type=? AND event_type!='lead_submit'
                  AND json_extract(attr_json,'$.{dist_attr}') IS NOT NULL
                GROUP BY user_id
                HAVING COUNT(DISTINCT json_extract(attr_json,'$.{dist_attr}')) {op} ?
            """
            return {row[0] for row in con.execute(sql, [event, int(val)]).fetchall()}

        raise ValueError(f"未知 raw 属性: {attr!r}")

    # ── 主 eval ────────────────────────────────────────────────────────────

    def eval(self, node: ASTNode) -> set[str]:
        if isinstance(node, AndNode):
            left = self.eval(node.left)
            if not left:
                return set()
            return left & self.eval(node.right)
        if isinstance(node, OrNode):
            return self.eval(node.left) | self.eval(node.right)
        if isinstance(node, NotNode):
            return self._all_users() - self.eval(node.operand)
        if isinstance(node, EventCondNode):
            return self._eval_event(node)
        if isinstance(node, ProfileCondNode):
            return self._eval_profile(node)
        if isinstance(node, RawCondNode):
            return self._eval_raw(node)
        raise ValueError(f"未知 AST 节点: {type(node)}")


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _cmp(a: float, op: str, b: float) -> bool:
    return {">=": a>=b, "<=": a<=b, ">": a>b, "<": a<b, "=": a==b, "!=": a!=b}.get(op, False)


def _build_attr_where(filt: dict | None) -> tuple[str, list]:
    """将属性过滤 dict 转为 SQL WHERE 片段和参数列表"""
    if not filt or filt["mode"] != "filter":
        return "", []
    attr, op, val = filt["attr"], filt["op"], filt["val"]
    json_path = f"json_extract(attr_json,'$.{attr}')"
    if val is None:  # !=null 或 =null
        if op == "!=":
            return f" AND {json_path} IS NOT NULL", []
        else:
            return f" AND {json_path} IS NULL", []
    return f" AND {json_path} {op} ?", [val]


def _raw_user_sql(event: str, filt: dict | None, agg: str) -> str:
    """生成 SELECT user_id, {agg} val FROM user_raw_events WHERE ... GROUP BY user_id"""
    where_extra, _ = _build_attr_where(filt)
    # 注意：filt 参数目前不含外部参数，before/same 的 filter 暂只支持 IS NOT NULL 类
    return f"""
        SELECT user_id, {agg} val FROM user_raw_events
        WHERE event_type='{event}' AND event_type!='lead_submit'{where_extra}
        GROUP BY user_id
    """


# ─────────────────────────────────────────────────────────────────────────────
# 公共接口
# ─────────────────────────────────────────────────────────────────────────────

def eval_expr(expr: str, con: sqlite3.Connection) -> set[str]:
    """解析并执行规则表达式，返回命中的 user_id 集合"""
    ast = parse_expr(expr)
    return Executor(con).eval(ast)


def validate_expr(expr: str) -> tuple[bool, str]:
    """只做语法检查，不执行。返回 (ok, error_msg)"""
    try:
        parse_expr(expr)
        return True, ""
    except (SyntaxError, ValueError) as e:
        return False, str(e)


def extract_event_names(expr: str) -> list[str]:
    """
    从规则表达式中提取所有引用的 event.<name> 标识符列表（去重，保序）。
    用于 Need 打分时确定该 Need 依赖哪些 Action 事件。

    示例：
      "event.Action_Foo.exists AND event.Action_Bar.count >= 1"
      → ["Action_Foo", "Action_Bar"]
    """
    try:
        ast = parse_expr(expr)
    except Exception:
        return []

    seen: list[str] = []
    visited: set[str] = set()

    def _walk(node: ASTNode) -> None:
        if isinstance(node, (AndNode, OrNode)):
            _walk(node.left)
            _walk(node.right)
        elif isinstance(node, NotNode):
            _walk(node.operand)
        elif isinstance(node, EventCondNode):
            if node.event_type not in visited:
                visited.add(node.event_type)
                seen.append(node.event_type)

    _walk(ast)
    return seen
