import main


def test_call_deepseek_ga_for_chunks_distributes_work_and_adds_locator(monkeypatch):
    calls = []

    def fake_single_chunk(text_for_model, num_questions, system_prompt=None, log_fn=print):
        calls.append((text_for_model, num_questions, system_prompt))
        return [
            {
                "id": f"q{len(calls)}",
                "question": "Question?",
                "ga_answer": "Answer",
                "source_locator": "manual section",
            }
        ], None

    monkeypatch.setattr(main, "call_deepseek_ga_single_chunk", fake_single_chunk)

    pairs, errors = main.call_deepseek_ga_for_chunks(
        [
            {"index": 0, "title": "A", "text": "alpha"},
            {"index": 1, "title": "B", "text": "beta"},
        ],
        total_questions=5,
        system_prompt="custom",
        log_fn=lambda message: None,
    )

    assert errors == []
    assert [call[1] for call in calls] == [3, 2]
    assert len(pairs) == 2
    assert "manual section" in pairs[0]["source_locator"]
    assert "分片0" in pairs[0]["source_locator"]
