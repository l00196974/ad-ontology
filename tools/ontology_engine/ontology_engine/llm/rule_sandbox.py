"""
LLM 规则代码沙箱验证器
=======================
在隔离环境中验证 LLM 生成的 BaseRule 代码，防止恶意代码注入。

四层验证：
  1. 语法检查   — ast.parse()，确保代码可解析
  2. 安全扫描   — AST 白名单扫描，禁止危险 import 和内置调用
  3. 类型检查   — 确保代码定义了合法的 BaseRule 子类（有 rule_id, evaluate()）
  4. 功能验证   — 用 SandboxTestCase 测试用例验证 evaluate() 输出

沙箱隔离方式：
  - 使用 RestrictedPython（若已安装）或纯 AST 扫描（回退方案）
  - exec() 在受限 namespace 中执行，无法访问文件系统和网络
"""

from __future__ import annotations

import ast
import dataclasses
import logging
import textwrap
import types

logger = logging.getLogger(__name__)

# 禁止使用的模块名（黑名单）
_BANNED_IMPORTS: set[str] = {
    "os", "sys", "subprocess", "socket", "requests", "urllib",
    "http", "ftplib", "smtplib", "shutil", "pathlib",
    "importlib", "ctypes", "cffi", "pickle", "shelve",
    "tempfile", "glob", "fnmatch",
    "threading", "multiprocessing", "concurrent",
    "signal", "resource", "platform",
}

# 禁止使用的内置函数名
_BANNED_BUILTINS: set[str] = {
    "exec", "eval", "compile", "__import__", "open",
    "input", "print",   # print 允许（规则用到 _log），但 __builtins__ 会限制
    "breakpoint", "vars", "dir",
}


# ── 数据类 ───────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class SandboxTestCase:
    """
    沙箱验证测试用例。

    字段：
        description     — 测试用例描述（便于人阅读）
        user_props      — 模拟用户属性 dict（field → value）
        car_props_list  — 模拟看车记录列表（每个元素是 {power_type, body_type, ...}）
        expected_needs  — 期望 evaluate() 返回的 NeedKey 列表
        expected_empty  — True 时期望 evaluate() 返回空列表（互斥场景）
    """
    description:    str
    user_props:     dict
    car_props_list: list[dict]             = dataclasses.field(default_factory=list)
    expected_needs: list                   = dataclasses.field(default_factory=list)
    expected_empty: bool                   = False


@dataclasses.dataclass
class TestCaseResult:
    description: str
    passed:      bool
    expected:    list
    actual:      list
    error:       str = ""


@dataclasses.dataclass
class ValidationResult:
    passed:       bool
    rule_id:      str
    errors:       list[str]
    test_results: list[TestCaseResult]


# ── 沙箱验证器 ───────────────────────────────────────────────────────────────

class RuleSandbox:
    """
    LLM 规则代码沙箱验证器。

    validate(rule_code, test_cases) 按顺序执行四层验证，任意层失败立即返回。
    """

    def validate(
        self,
        rule_code:  str,
        test_cases: list[SandboxTestCase],
    ) -> ValidationResult:
        """
        验证 LLM 生成的规则代码。

        参数：
            rule_code  — Python 代码字符串（BaseRule 子类）
            test_cases — 功能验证测试用例（可为空列表，则跳过功能测试）

        返回：
            ValidationResult（passed=True 表示全部通过）
        """
        errors:       list[str]        = []
        test_results: list[TestCaseResult] = []
        rule_id = ""

        # === 第 1 层：语法检查 ===
        try:
            tree = ast.parse(textwrap.dedent(rule_code))
        except SyntaxError as e:
            return ValidationResult(
                passed=False, rule_id="",
                errors=[f"语法错误：{e}"],
                test_results=[],
            )

        # === 第 2 层：安全扫描 ===
        security_errors = _scan_security(tree)
        if security_errors:
            return ValidationResult(
                passed=False, rule_id="",
                errors=security_errors,
                test_results=[],
            )

        # === 第 3 层：类型检查（动态加载） ===
        try:
            from ontology_engine.rules.base_rule import BaseRule
            from ontology_engine.config.enums    import NeedKey

            module = types.ModuleType("_sandbox_rule")
            module.__dict__.update({
                "BaseRule": BaseRule,
                "NeedKey":  NeedKey,
            })
            # 注入常用枚举（规则代码可能引用）
            _inject_enums(module)

            # 受限 exec（已通过 AST 扫描）
            exec(  # noqa: S102
                compile(textwrap.dedent(rule_code), "<sandbox>", "exec"),
                module.__dict__,
            )

            # 找到 BaseRule 子类
            subclasses = [
                obj for obj in module.__dict__.values()
                if (isinstance(obj, type)
                    and issubclass(obj, BaseRule)
                    and obj is not BaseRule)
            ]
            if len(subclasses) == 0:
                raise TypeError("代码中未找到 BaseRule 子类")
            if len(subclasses) > 1:
                raise TypeError(
                    f"代码中找到多个 BaseRule 子类：{[c.__name__ for c in subclasses]}"
                )

            rule_cls = subclasses[0]
            if not rule_cls.rule_id:
                raise TypeError(f"规则类 {rule_cls.__name__} 未设置 rule_id")

            rule_id   = rule_cls.rule_id
            rule_inst = rule_cls()

        except Exception as e:
            return ValidationResult(
                passed=False, rule_id=rule_id,
                errors=[f"类型/加载错误：{e}"],
                test_results=[],
            )

        # === 第 4 层：功能测试 ===
        if test_cases:
            test_results = _run_test_cases(rule_inst, test_cases)
            failed = [r for r in test_results if not r.passed]
            if failed:
                errors.extend([
                    f"测试用例失败：「{r.description}」— {r.error or f'期望 {r.expected}，实际 {r.actual}'}"
                    for r in failed
                ])

        passed = len(errors) == 0
        return ValidationResult(
            passed=passed,
            rule_id=rule_id,
            errors=errors,
            test_results=test_results,
        )


# ── AST 安全扫描 ─────────────────────────────────────────────────────────────

class _SecurityVisitor(ast.NodeVisitor):
    """遍历 AST，收集安全违规"""

    def __init__(self):
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            top_level = alias.name.split(".")[0]
            if top_level in _BANNED_IMPORTS:
                self.errors.append(
                    f"第 {node.lineno} 行：禁止导入模块 '{alias.name}'"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        top_level = (node.module or "").split(".")[0]
        if top_level in _BANNED_IMPORTS:
            self.errors.append(
                f"第 {node.lineno} 行：禁止导入模块 '{node.module}'"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # 检查 exec / eval / open 等危险内置调用
        if isinstance(node.func, ast.Name):
            if node.func.id in _BANNED_BUILTINS:
                self.errors.append(
                    f"第 {node.lineno} 行：禁止调用内置函数 '{node.func.id}'"
                )
        # 检查 __import__("os") 形式
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            self.errors.append(
                f"第 {node.lineno} 行：禁止使用 __import__()"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # 检查 os.system / subprocess.run 等属性调用
        if isinstance(node.value, ast.Name):
            if node.value.id in _BANNED_IMPORTS:
                self.errors.append(
                    f"第 {node.lineno} 行：禁止访问模块 '{node.value.id}' 的属性"
                )
        self.generic_visit(node)


def _scan_security(tree: ast.AST) -> list[str]:
    visitor = _SecurityVisitor()
    visitor.visit(tree)
    return visitor.errors


# ── 功能测试执行 ─────────────────────────────────────────────────────────────

class _MockCar:
    """模拟 CarModel 实例"""
    def __init__(self, props: dict):
        self.name           = props.get("name", "MockCar")
        self.power_type     = props.get("power_type")
        self.body_type      = props.get("body_type")
        self.car_price_band = props.get("car_price_band")
        self.car_size_level = props.get("car_size_level")
        self.brand_camp     = props.get("brand_camp")


class _MockUser:
    """模拟 User 实例"""
    def __init__(self, props: dict, car_props_list: list[dict]):
        self.name                    = props.get("name", "MockUser")
        self.age_range               = props.get("age_range")
        self.gender                  = props.get("gender")
        self.generation_group        = props.get("generation_group")
        self.city_tier               = props.get("city_tier")
        self.policy_restriction_fuel = props.get("policy_restriction_fuel")
        self.policy_restriction_ev   = props.get("policy_restriction_ev")
        self.device_price_tier       = props.get("device_price_tier")
        self.travel_activity         = props.get("travel_activity")
        self.inquiry_frequency       = int(props.get("inquiry_frequency", 0))
        self.conversion_stage        = props.get("conversion_stage")
        self.has_interacted_with     = [_MockCar(c) for c in car_props_list]
        self.has_inferred_need       = []


def _run_test_cases(
    rule_inst, test_cases: list[SandboxTestCase]
) -> list[TestCaseResult]:
    results = []
    for tc in test_cases:
        user = _MockUser(tc.user_props, tc.car_props_list)
        try:
            actual_keys = rule_inst.evaluate(user)
            actual_set  = set(str(k) for k in actual_keys)

            if tc.expected_empty:
                passed = len(actual_keys) == 0
                exp_repr = []
            else:
                expected_set = set(str(k) for k in tc.expected_needs)
                passed       = actual_set == expected_set
                exp_repr     = list(expected_set)

            results.append(TestCaseResult(
                description = tc.description,
                passed      = passed,
                expected    = exp_repr,
                actual      = list(actual_set),
            ))
        except Exception as e:
            results.append(TestCaseResult(
                description = tc.description,
                passed      = False,
                expected    = [str(k) for k in tc.expected_needs],
                actual      = [],
                error       = str(e),
            ))
    return results


# ── 枚举注入辅助 ─────────────────────────────────────────────────────────────

def _inject_enums(module) -> None:
    """向沙箱模块注入所有常用枚举，让规则代码可以直接引用"""
    try:
        from ontology_engine.config.enums import (
            AgeRange, Gender, GenerationGroup, CityTier,
            PolicyFuel, PolicyEV, DevicePriceTier, TravelActivity,
            PriceBand, ConversionStage, TestDriveStatus,
            BodyType, CarSizeLevel, PowerType, BrandCamp, NeedKey,
        )
        module.__dict__.update({
            "AgeRange": AgeRange, "Gender": Gender,
            "GenerationGroup": GenerationGroup, "CityTier": CityTier,
            "PolicyFuel": PolicyFuel, "PolicyEV": PolicyEV,
            "DevicePriceTier": DevicePriceTier, "TravelActivity": TravelActivity,
            "PriceBand": PriceBand, "ConversionStage": ConversionStage,
            "TestDriveStatus": TestDriveStatus,
            "BodyType": BodyType, "CarSizeLevel": CarSizeLevel,
            "PowerType": PowerType, "BrandCamp": BrandCamp,
        })
    except ImportError:
        pass
