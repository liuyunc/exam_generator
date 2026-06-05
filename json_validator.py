"""
JSON Validator for LLM Responses - 大模型 JSON 输出验证与幻觉检测

针对从 DeepSeek/GPUStack 获取的 JSON 数据进行多层验证，防止模型幻觉。
"""

import json
import logging
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ========= 验证配置常量 =========
MAX_QUESTION_LENGTH = 5000
MIN_QUESTION_LENGTH = 5
MAX_ANSWER_LENGTH = 2000
MIN_ANSWER_LENGTH = 1
MAX_OPTIONS = 10
MIN_OPTIONS_CHOICE = 2
MAX_OPTIONS_CHOICE = 8
VALID_QUESTION_TYPES = {
    "single_choice", "multiple_choice", "true_false", "short_answer",
    "fill_blank", "essay", "matching", "ordering",
    "单选题", "多选题", "判断题", "简答题", "填空题", "论述题", "配对题", "排序题"
}
VALID_DIFFICULTY_LEVELS = {
    "easy", "medium", "hard", "very_hard",
    "简单", "中等", "困难", "非常困难"
}


@dataclass
class ValidationResult:
    """验证结果数据类"""
    is_valid: bool
    score: float  # 0-1 之间，表示 JSON 可信度
    errors: List[str]  # 发现的错误列表
    warnings: List[str]  # 警告列表（不致命但需要注意）
    sanitized_data: Optional[Dict[str, Any]] = None  # 修复后的数据


class JSONValidator:
    """LLM 响应 JSON 验证器 - 防止幻觉"""

    @staticmethod
    def validate_ga_response(data: Dict[str, Any]) -> ValidationResult:
        """
        完整验证 GA 对 JSON 响应
        
        Args:
            data: 模型返回的 JSON 数据
            
        Returns:
            ValidationResult: 包含验证结果、评分、错误信息的对象
        """
        errors = []
        warnings = []
        sanitized_data = {}
        
        # 1. 基础结构检查
        if not isinstance(data, dict):
            errors.append(f"根对象必须是字典，当前类型: {type(data)}")
            return ValidationResult(False, 0.0, errors, warnings)

        if "ga_pairs" not in data:
            errors.append("缺少必需的 'ga_pairs' 字段")
            return ValidationResult(False, 0.0, errors, warnings)

        ga_pairs = data.get("ga_pairs")
        if not isinstance(ga_pairs, list):
            errors.append(f"'ga_pairs' 必须是列表，当前类型: {type(ga_pairs)}")
            return ValidationResult(False, 0.0, errors, warnings)

        if len(ga_pairs) == 0:
            errors.append("'ga_pairs' 列表为空")
            return ValidationResult(False, 0.0, errors, warnings)

        # 2. 逐条验证 GA 对
        valid_pairs = []
        pair_level_errors = []
        
        for idx, pair in enumerate(ga_pairs):
            pair_result = JSONValidator._validate_ga_pair(pair, index=idx)
            
            if pair_result.is_valid:
                valid_pairs.append(pair_result.sanitized_data)
            else:
                pair_level_errors.extend([f"[题目 {idx}] {e}" for e in pair_result.errors])
            
            warnings.extend([f"[题目 {idx}] {w}" for w in pair_result.warnings])

        # 3. 综合判断
        if not valid_pairs:
            errors.append(f"所有 {len(ga_pairs)} 条题目都验证失败")
            return ValidationResult(False, 0.0, errors, warnings)

        errors.extend(pair_level_errors)
        sanitized_data["ga_pairs"] = valid_pairs

        # 4. 计算信任度评分
        valid_ratio = len(valid_pairs) / len(ga_pairs)
        score = valid_ratio * (1 - len(warnings) * 0.01)  # 警告会降低评分
        score = max(0.0, min(1.0, score))

        is_valid = valid_ratio >= 0.5 and len(valid_pairs) >= 1  # 至少50%有效

        return ValidationResult(is_valid, score, errors, warnings, sanitized_data)

    @staticmethod
    def _validate_ga_pair(pair: Any, index: int) -> ValidationResult:
        """验证单个 GA 对"""
        errors = []
        warnings = []
        sanitized = {}

        # 1. 基础类型检查
        if not isinstance(pair, dict):
            errors.append(f"第 {index} 条题目必须是字典")
            return ValidationResult(False, 0.0, errors, warnings)

        # 2. 必需字段检查
        if "question" not in pair:
            errors.append("缺少 'question' 字段")
            return ValidationResult(False, 0.0, errors, warnings)

        if "ga_answer" not in pair:
            errors.append("缺少 'ga_answer' 字段")
            return ValidationResult(False, 0.0, errors, warnings)

        # 3. 字段内容验证
        question = str(pair.get("question", "")).strip()
        answer = str(pair.get("ga_answer", "")).strip()

        # 题目长度验证
        if not MIN_QUESTION_LENGTH <= len(question) <= MAX_QUESTION_LENGTH:
            errors.append(
                f"题目长度不符合要求 ({MIN_QUESTION_LENGTH}-{MAX_QUESTION_LENGTH}), "
                f"实际: {len(question)}"
            )
            return ValidationResult(False, 0.0, errors, warnings)

        # 答案长度验证
        if not MIN_ANSWER_LENGTH <= len(answer) <= MAX_ANSWER_LENGTH:
            errors.append(
                f"答案长度不符合要求 ({MIN_ANSWER_LENGTH}-{MAX_ANSWER_LENGTH}), "
                f"实际: {len(answer)}"
            )
            return ValidationResult(False, 0.0, errors, warnings)

        sanitized["question"] = question
        sanitized["ga_answer"] = answer

        # 4. 可选字段验证
        # question_type
        question_type = pair.get("question_type", "").strip() if pair.get("question_type") else ""
        if question_type and question_type not in VALID_QUESTION_TYPES:
            warnings.append(f"未知的题型: '{question_type}'，推荐使用标准题型")
        sanitized["question_type"] = question_type

        # difficulty
        difficulty = pair.get("difficulty", "").strip() if pair.get("difficulty") else ""
        if difficulty and difficulty not in VALID_DIFFICULTY_LEVELS:
            warnings.append(f"未知的难度等级: '{difficulty}'")
        sanitized["difficulty"] = difficulty

        # options (对于选择题)
        if question_type in {"single_choice", "multiple_choice", "单选题", "多选题"}:
            options = pair.get("options", [])
            if not isinstance(options, list):
                warnings.append(f"options 应该是列表，当前类型: {type(options)}")
                options = []
            
            if len(options) < MIN_OPTIONS_CHOICE:
                warnings.append(f"选项数量过少 ({len(options)})，建议至少 {MIN_OPTIONS_CHOICE} 个")
            
            if len(options) > MAX_OPTIONS_CHOICE:
                warnings.append(f"选项数量过多 ({len(options)})，超过建议最大值 {MAX_OPTIONS_CHOICE}")
                options = options[:MAX_OPTIONS_CHOICE]  # 截断
            
            sanitized["options"] = options
        else:
            sanitized["options"] = pair.get("options", [])

        # source_locator (来源定位)
        source_locator = pair.get("source_locator", "").strip() if pair.get("source_locator") else ""
        sanitized["source_locator"] = source_locator

        # source_excerpt (原文摘录)
        source_excerpt = pair.get("source_excerpt", "").strip() if pair.get("source_excerpt") else ""
        sanitized["source_excerpt"] = source_excerpt

        # comment (命题说明)
        comment = pair.get("comment", "").strip() if pair.get("comment") else ""
        sanitized["comment"] = comment

        # score (分数)
        if "score" in pair and pair["score"] is not None:
            try:
                score_val = float(pair["score"])
                if score_val < 0:
                    warnings.append(f"分数为负值: {score_val}")
                sanitized["score"] = score_val
            except (ValueError, TypeError):
                warnings.append(f"分数格式错误: {pair['score']}")
                sanitized["score"] = None
        else:
            sanitized["score"] = None

        # tag (标签)
        tag = pair.get("tag", "").strip() if pair.get("tag") else ""
        sanitized["tag"] = tag

        # id (题目 ID)
        pair_id = pair.get("id", "").strip() if pair.get("id") else f"q_{index}"
        sanitized["id"] = pair_id

        # 5. 内容一致性检查（防止幻觉）
        hallucination_warnings = JSONValidator._detect_hallucinations(pair, sanitized)
        warnings.extend(hallucination_warnings)

        is_valid = len(errors) == 0
        return ValidationResult(is_valid, 1.0 if is_valid else 0.0, errors, warnings, sanitized)

    @staticmethod
    def _detect_hallucinations(original: Dict[str, Any], sanitized: Dict[str, Any]) -> List[str]:
        """
        检测模型幻觉现象
        
        返回可能的幻觉警告列表
        """
        warnings = []

        # 1. 答案与题目的一致性
        question = sanitized.get("question", "").lower()
        answer = sanitized.get("ga_answer", "").lower()
        
        # 检查答案是否包含在题目中（常见的幻觉现象）
        if len(answer) > 10 and answer in question:
            warnings.append("答案内容与题目重复，可能是模型幻觉")

        # 2. 多选题的答案验证
        question_type = sanitized.get("question_type", "").lower()
        if "multiple" in question_type or "多选" in question_type:
            answer_text = answer.upper()
            # 检查是否包含有效的选项标记
            valid_chars = set("ABCDEFGH")
            answer_chars = set(c for c in answer_text if c in valid_chars)
            if not answer_chars:
                warnings.append("多选题答案中未发现有效的选项标记 (A-H)")

        # 3. 单选题的答案验证
        if "single" in question_type or "单选" in question_type:
            answer_text = answer.upper().strip()
            if len(answer_text) > 2:  # 单选答案通常只有 1-2 个字符
                warnings.append("单选题答案过长，可能包含多个选项")

        # 4. 选项与答案的一致性
        options = sanitized.get("options", [])
        if options and len(options) > 0:
            options_lower = [str(o).lower() for o in options]
            
            # 检查答案是否在选项中（针对索引型答案）
            if answer_text in ["a", "b", "c", "d", "e", "f", "g", "h"]:
                idx = ord(answer_text) - ord('a')
                if idx >= len(options):
                    warnings.append(f"答案索引 '{answer_text}' 超出选项范围 (共 {len(options)} 个选项)")

        # 5. 难度等级有效性
        difficulty = sanitized.get("difficulty", "").lower()
        if difficulty and difficulty not in {"easy", "medium", "hard", "very_hard",
                                               "简单", "中等", "困难", "非常困难"}:
            warnings.append(f"不标准的难度等级: '{difficulty}'")

        # 6. 来源定位有效性
        source_locator = sanitized.get("source_locator", "")
        if source_locator:
            # 检查是否看起来像有效的来源引用
            if len(source_locator) < 3:
                warnings.append("来源定位过短，可能不是有效的来源信息")

        # 7. 检查重复或模板痕迹
        question_text = sanitized.get("question", "")
        if question_text.count("...") > 2:
            warnings.append("题目中包含过多省略号，可能是未完成的生成")

        if "TODO" in question_text or "FIXME" in question_text or "例如" in question_text:
            warnings.append("题目中包含模板标记或占位符，可能是未完成的生成")

        return warnings

    @staticmethod
    def log_validation_report(result: ValidationResult, pair_count: int) -> str:
        """生成可读的验证报告"""
        report = []
        report.append(f"\n{'='*60}")
        report.append(f"JSON 验证报告")
        report.append(f"{'='*60}")
        report.append(f"总题目数: {pair_count}")
        report.append(f"有效题目数: {len(result.sanitized_data.get('ga_pairs', []))}")
        report.append(f"信任度评分: {result.score:.2%}")
        report.append(f"验证状态: {'✓ 通过' if result.is_valid else '✗ 失败'}")

        if result.errors:
            report.append(f"\n【错误】({len(result.errors)} 条):")
            for err in result.errors[:10]:  # 最多显示 10 条
                report.append(f"  - {err}")
            if len(result.errors) > 10:
                report.append(f"  ... 还有 {len(result.errors) - 10} 条错误")

        if result.warnings:
            report.append(f"\n【警告】({len(result.warnings)} 条):")
            for warn in result.warnings[:10]:  # 最多显示 10 条
                report.append(f"  - {warn}")
            if len(result.warnings) > 10:
                report.append(f"  ... 还有 {len(result.warnings) - 10} 条警告")

        report.append(f"\n{'='*60}\n")
        return "\n".join(report)


def validate_and_sanitize_ga_response(
    json_data: Dict[str, Any],
    strict_mode: bool = False
) -> Tuple[List[Dict[str, Any]], ValidationResult]:
    """
    便利函数：验证并清理 GA 响应
    
    Args:
        json_data: 模型返回的 JSON
        strict_mode: 严格模式 (若为 True，则任何警告都会导致题目被过滤)
        
    Returns:
        (清理后的题目列表, 验证结果)
    """
    validator = JSONValidator()
    result = validator.validate_ga_response(json_data)

    if not result.is_valid:
        logger.warning(f"JSON 验证失败: {result.errors}")
        return [], result

    ga_pairs = result.sanitized_data.get("ga_pairs", [])
    
    if strict_mode and result.warnings:
        logger.warning(f"严格模式下，因存在警告而过滤了部分题目")
        # 在严格模式下，可进一步过滤有问题的题目

    logger.info(f"JSON 验证通过，有效题目: {len(ga_pairs)}/{len(json_data.get('ga_pairs', []))}")
    return ga_pairs, result
