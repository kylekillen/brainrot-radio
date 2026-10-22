"""story_research.py: headline-only brief items are researched or dropped (Kyle 2026-10-22)."""
import story_research as sr

BRIEF = """# Topic Brief

## 1. Big essay
Source: Latent Space | Topic: ai | Age: today | Score: 8
Type: substack (full text (8574 words))
Full article: /tmp/x.txt

body

---

## 2. Barclays plans to cut 5,000 jobs as part of AI-driven cost cutting (William Shaw/Bloomberg)
Source: Techmeme | Topic: ai | Age: today | Score: 3
Link: https://www.techmeme.com/x

William Shaw / Bloomberg : Barclays plans to cut 5,000 jobs

---

## 3. Obscure thing nobody covered
Source: Techmeme | Topic: ai | Age: today | Score: 2
Link: https://www.techmeme.com/y

Obscure thing nobody covered

---

## 4. [Podcast] Some episode
Source: Pod | Topic: x | Age: today | Score: 1
Type: podcast (no transcript)

desc

---

═══ X PULSE ═══
## 1. Feed read heading stays untouched
"""

PROSE = "".join(f"Paragraph {i}: Barclays said on Thursday it plans to cut 5,000 jobs across the bank as "
                "artificial intelligence drives cost cutting in support functions and developer roles.\n"
                for i in range(12))


def fake_search(q, n):
    if "Barclays" in q:
        return {"results": [{"title": "Barclays cuts", "url": "https://cnbc.com/a", "snippet": "5,000 jobs"}]}
    return {"results": []}


def fake_fetch(url, n):
    return {"text": PROSE, "backend": "http"}


def test_parse_stops_at_x_pulse_banner():
    head, items, tail = sr.parse_brief(BRIEF)
    assert [n for n, _, _ in items] == ["1", "2", "3", "4"]
    assert tail.startswith("═══") and "Feed read heading" in tail


def test_classify():
    _, items, _ = sr.parse_brief(BRIEF)
    assert [sr.classify(b) for _, _, b in items] == ["has_text", "thin", "thin", "podcast_no_transcript"]


def test_researched_item_gets_real_text_and_label():
    _, items, _ = sr.parse_brief(BRIEF)
    n, t, b = items[1]
    r = sr.research(t, b, fake_search, fake_fetch)
    assert r["ok"] and r["sources"][0][0] == "https://cnbc.com/a"
    out = sr.rewrite_item(b, r)
    assert "Type: researched (full text from 1 web sources)" in out
    assert "Barclays said on Thursday" in out
    assert out.startswith("## 2. Barclays")


def test_unresearchable_item_fails_and_aggregator_hosts_are_skipped():
    _, items, _ = sr.parse_brief(BRIEF)
    _, t, b = items[2]
    fetched = []
    r = sr.research(t, b, fake_search, lambda u, n: fetched.append(u) or {"text": ""})
    assert not r["ok"]
    assert not any("techmeme" in u for u in fetched)


def test_irrelevant_page_is_not_evidence():
    _, items, _ = sr.parse_brief(BRIEF)
    _, t, b = items[1]
    other = "".join(f"{i} The weather in Paris was mild this week with light rain expected through Sunday evening.\n" for i in range(20))
    r = sr.research(t, b, fake_search, lambda u, n: {"text": other})
    assert not r["ok"]
