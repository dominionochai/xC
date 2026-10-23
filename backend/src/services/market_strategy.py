"""Pure, deterministic culture-economics planning and analysis primitives."""
from __future__ import annotations
from dataclasses import dataclass
import math
import textwrap
import unicodedata
from typing import Mapping, Sequence

NEIGHBORHOOD_NAMES = ("SoHo NYC", "Shibuya Tokyo", "Mayfair London")

@dataclass(frozen=True)
class TransitionStep:
    number: int
    phase: str
    from_category: str
    to_category: str
    objective: str

@dataclass(frozen=True)
class TransitionCampaign:
    source_category: str
    middleman_categories: tuple[str, str]
    target_category: str
    steps: tuple[TransitionStep, ...]

def _label(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()

def build_transition_campaign(source_category: str, target_category: str,
                              middleman_categories: Sequence[str]) -> TransitionCampaign:
    """Build source -> middleman 1 -> middleman 2 -> target as 3 directed steps.

    The caller supplies all category relationships: exactly two distinct
    middlemen are required, with all four labels unique case-insensitively.
    Fixed objectives describe a generic adoption sequence, not proven outcomes.
    """
    source, target = _label(source_category, "source_category"), _label(target_category, "target_category")
    if isinstance(middleman_categories, (str, bytes)) or len(middleman_categories) != 2:
        raise ValueError("middleman_categories must contain exactly two labels")
    middle = tuple(_label(x, "middleman category") for x in middleman_categories)
    labels = (source, *middle, target)
    if len({x.casefold() for x in labels}) != 4:
        raise ValueError("source, middleman, and target categories must be distinct")
    edges = ((source, middle[0]), (middle[0], middle[1]), (middle[1], target))
    phases = ("Familiarization", "Bridge adoption", "Conversion")
    objectives = (
        f"Build familiarity with {middle[0]} among people engaging with {source}.",
        f"Use {middle[1]} as the next bridge from {middle[0]}.",
        f"Invite adoption of {target} from the established {middle[1]} bridge.",
    )
    steps = tuple(TransitionStep(i, phases[i-1], a, b, objectives[i-1])
                  for i, (a, b) in enumerate(edges, 1))
    return TransitionCampaign(source, (middle[0], middle[1]), target, steps)

@dataclass(frozen=True)
class NeighborhoodAffinity:
    neighborhood: str
    cosine_similarity: float
    score: float

def _vector(vector: Mapping[str, float], field: str,
            expected: set[str] | None = None) -> dict[str, float]:
    if not isinstance(vector, Mapping) or not vector:
        raise ValueError(f"{field} must be a non-empty feature mapping")
    if any(not isinstance(k, str) or not k.strip() for k in vector):
        raise ValueError(f"{field} keys must be non-empty strings")
    if expected is not None and set(vector) != expected:
        raise ValueError(f"{field} must use exactly the input feature names")
    result = {}
    for key, value in vector.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field}[{key!r}] must be finite and non-negative")
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{field}[{key!r}] must be finite and non-negative")
        result[key] = value
    if not any(result.values()):
        raise ValueError(f"{field} must have non-zero norm")
    return result

def score_neighborhood_affinities(input_vector: Mapping[str, float],
                                  neighborhood_vectors: Mapping[str, Mapping[str, float]]) -> tuple[NeighborhoodAffinity, ...]:
    """Score supplied vectors using 100*cosine(input, location), clamped to [0,100].

    All feature values must be finite and non-negative, names must match, and
    vectors must be non-zero. The three named neighborhood vectors are required;
    no city data or hidden weights are embedded in this calculation.
    """
    source = _vector(input_vector, "input_vector")
    if not isinstance(neighborhood_vectors, Mapping) or set(neighborhood_vectors) != set(NEIGHBORHOOD_NAMES):
        raise ValueError(f"neighborhood_vectors must contain exactly {NEIGHBORHOOD_NAMES}")
    keys = sorted(source)
    norm = math.sqrt(math.fsum(source[k]**2 for k in keys))
    result = []
    for name in NEIGHBORHOOD_NAMES:
        ref = _vector(neighborhood_vectors[name], name, set(source))
        ref_norm = math.sqrt(math.fsum(ref[k]**2 for k in keys))
        cosine = min(1.0, max(0.0, math.fsum(source[k]*ref[k] for k in keys)/(norm*ref_norm)))
        cosine = round(cosine, 8)
        result.append(NeighborhoodAffinity(name, cosine, round(cosine*100, 6)))
    return tuple(result)

@dataclass(frozen=True)
class TAMEstimate:
    eligible_customers: int
    annual_spend_per_customer_usd: float
    penetration_rate: float
    tam_usd: float
    obtainable_market_usd: float

def _number(value: float, field: str, low: float, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < low or (high is not None and value > high):
        raise ValueError(f"{field} must be finite and in the allowed range")
    return value

def estimate_tam(eligible_customers: int, annual_spend_per_customer_usd: float,
                 penetration_rate: float) -> TAMEstimate:
    """Use TAM=count*annual spend; obtainable scenario=TAM*penetration.

    Count is a non-negative integer, spend is finite/non-negative, and
    penetration is finite in [0,1]. This is a supplied-assumption estimate,
    not an externally sourced market size or forecast.
    """
    if isinstance(eligible_customers, bool) or not isinstance(eligible_customers, int) or eligible_customers < 0:
        raise ValueError("eligible_customers must be a non-negative integer")
    spend = _number(annual_spend_per_customer_usd, "annual_spend_per_customer_usd", 0)
    penetration = _number(penetration_rate, "penetration_rate", 0, 1)
    tam = eligible_customers * spend
    return TAMEstimate(eligible_customers, spend, penetration, tam, tam*penetration)

@dataclass(frozen=True)
class PanderingAuthenticityRisk:
    score: float
    contradiction: float
    overclaim: float
    alignment_gap: float

def pandering_authenticity_risk(co_occurrence: Sequence[float],
                                anti_co_occurrence: Sequence[float],
                                affinity_vector: Sequence[float]) -> PanderingAuthenticityRisk:
    """Return the Pandering & Authenticity Risk Index, bounded to 0-100.

    For aligned equal-length vectors C, A, F in [0,1], score = 100 *
    (0.50*mean(A) + 0.30*max(0, mean(C)-mean(F)) +
    0.20*mean(abs(C_i-F_i))). Thus anti-co-occurrence is contradiction,
    excess co-occurrence over affinity is overclaim, and the absolute gap is
    misalignment. Equal, non-empty lengths and finite numeric inputs are required.
    """
    vectors = []
    for field, values in (("co_occurrence", co_occurrence),
                          ("anti_co_occurrence", anti_co_occurrence),
                          ("affinity_vector", affinity_vector)):
        if isinstance(values, (str, bytes)):
            raise ValueError(f"{field} must be a non-empty numeric sequence")
        try:
            raw = tuple(values)
        except TypeError as exc:
            raise ValueError(f"{field} must be a non-empty numeric sequence") from exc
        if not raw:
            raise ValueError(f"{field} must be non-empty")
        vectors.append(tuple(_number(x, f"{field}[{i}]", 0, 1) for i, x in enumerate(raw)))
    co, anti, affinity = vectors
    if len(co) != len(anti) or len(co) != len(affinity):
        raise ValueError("all risk vectors must have equal lengths")
    contradiction = math.fsum(anti)/len(anti)
    overclaim = max(0.0, math.fsum(co)/len(co) - math.fsum(affinity)/len(affinity))
    gap = math.fsum(abs(c-f) for c, f in zip(co, affinity))/len(co)
    score = min(100.0, max(0.0, 100*(.5*contradiction + .3*overclaim + .2*gap)))
    return PanderingAuthenticityRisk(round(score, 6), round(contradiction, 8),
                                     round(overclaim, 8), round(gap, 8))

@dataclass(frozen=True)
class InvestmentMemo:
    markdown: str
    pdf_bytes: bytes

def build_investment_memo(company_name: str, investment_thesis: str, tam: TAMEstimate,
                          affinity_scores: Sequence[NeighborhoodAffinity],
                          risk_index: PanderingAuthenticityRisk) -> InvestmentMemo:
    """Render a scenario-based institutional memo as Markdown and valid PDF 1.4 bytes.

    Figures and vectors come only from arguments; the memo is not a recommendation.
    PDF generation uses built-in Helvetica and the standard library (no ReportLab).
    """
    company, thesis = _label(company_name, "company_name"), _label(investment_thesis, "investment_thesis")
    if not isinstance(tam, TAMEstimate) or not isinstance(risk_index, PanderingAuthenticityRisk):
        raise ValueError("tam and risk_index must be estimator results")
    if not isinstance(affinity_scores, Sequence) or len(affinity_scores) != 3 or any(not isinstance(x, NeighborhoodAffinity) for x in affinity_scores):
        raise ValueError("affinity_scores must contain three NeighborhoodAffinity results")
    by_name = {x.neighborhood: x for x in affinity_scores}
    if len(by_name) != 3 or set(by_name) != set(NEIGHBORHOOD_NAMES):
        raise ValueError("affinity_scores must contain each named neighborhood exactly once")
    lines = [
        "# Institutional Investment Memo", "", f"**Company / scenario:** {company}",
        "**Purpose:** Assumption-driven culture-economics screening; not investment advice.", "",
        "## Executive summary", thesis,
        f"Supplied inputs imply annual TAM of ${tam.tam_usd:,.2f} and obtainable scenario of ${tam.obtainable_market_usd:,.2f}.",
        f"Pandering & Authenticity Risk Index: {risk_index.score:.2f}/100 (higher means greater modeled risk).", "",
        "## Market sizing and assumptions", f"- Eligible customers: {tam.eligible_customers:,}",
        f"- Annual spend per customer: ${tam.annual_spend_per_customer_usd:,.2f}",
        f"- Penetration assumption: {tam.penetration_rate:.2%}",
        "- Formula: TAM = eligible customers × annual spend per customer.",
        "- Obtainable scenario = TAM × penetration; neither figure is a forecast.", "",
        "## Supplied-vector neighborhood affinity", "Scores are cosine similarity mapped to 0-100, not evidence of demand.",
        "| Neighborhood | Cosine similarity | Score / 100 |", "|---|---:|---:|"]
    for name in NEIGHBORHOOD_NAMES:
        x = by_name[name]
        lines.append(f"| {name} | {x.cosine_similarity:.6f} | {x.score:.2f} |")
    lines += ["", "## Pandering & Authenticity Risk",
        "Formula: 100 × (0.50 × mean anti-co-occurrence + 0.30 × positive excess of mean co-occurrence over mean affinity + 0.20 × mean absolute co-occurrence/affinity gap).",
        f"- Index: {risk_index.score:.2f}/100", f"- Contradiction: {risk_index.contradiction:.6f}",
        f"- Overclaim: {risk_index.overclaim:.6f}", f"- Alignment gap: {risk_index.alignment_gap:.6f}", "",
        "## Investment committee considerations",
        "- Independently validate customer count, annual spend, and penetration assumptions.",
        "- Check that co-occurrence and anti-co-occurrence are aligned, comparable observations.",
        "- Treat neighborhood affinity as vector similarity, not evidence of revenue or market size.",
        "- No financials, valuation, or external market facts are asserted unless supplied above."]
    markdown = "\n".join(lines) + "\n"
    return InvestmentMemo(markdown, _minimal_pdf(markdown.splitlines()))

def _pdf_escape(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "replace").decode("ascii")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def _minimal_pdf(lines: Sequence[str]) -> bytes:
    """Create a multipage PDF with a correct xref table and no third-party dependency."""
    rendered = []
    for line in lines:
        rendered.extend(textwrap.wrap(line, 88, break_long_words=True) if line else [""])
    pages = [rendered[i:i+50] for i in range(0, len(rendered), 50)] or [[]]
    page_ids = [4+2*i for i in range(len(pages))]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
        (f"<< /Type /Pages /Kids [{' '.join(f'{n} 0 R' for n in page_ids)}] /Count {len(pages)} >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, lines_on_page in enumerate(pages):
        page_id, stream_id = 4+2*i, 5+2*i
        commands = ["BT", "/F1 10 Tf", "48 760 Td", "12 TL"]
        for line in lines_on_page:
            commands.extend((f"({_pdf_escape(line)}) Tj", "T*"))
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        objects.append(b"<< /Length "+str(len(stream)).encode()+b" >>\nstream\n"+stream+b"\nendstream")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for n, body in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{n} 0 obj\n".encode()+body+b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)
