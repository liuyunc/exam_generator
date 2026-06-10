import pytest
from json_validator import JSONValidator

def test_validate_ga_response_short_answer_no_unbound_local_error():
    validator = JSONValidator()
    # The fix ensures answer_text is defined for all question types
    # and correctly handles non-single/multiple choice options check
    result = validator.validate_ga_response({
        'ga_pairs': [
            {
                'question': 'What is 1+1?',
                'ga_answer': '2',
                'question_type': 'short_answer',
                'options': ['1', '2', '3']
            }
        ]
    })

    assert result.is_valid is True
    assert len(result.errors) == 0

def test_validate_ga_response_single_choice_invalid_answer():
    validator = JSONValidator()
    # Validates that 'answer_text' in ["A", "B"] checks correctly
    result = validator.validate_ga_response({
        'ga_pairs': [
            {
                'question': 'What is 1+1?',
                'ga_answer': 'd', # answer 'D' is out of bounds for 3 options
                'question_type': 'single_choice',
                'options': ['1', '2', '3']
            }
        ]
    })

    # We still accept it but emit a warning
    assert result.is_valid is True
    # Ensure warnings contains the out of bounds warning
    assert any("答案索引 'D' 超出选项范围" in w for w in result.warnings)
