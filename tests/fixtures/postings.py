"""Real-world-shaped sample postings used across the filter tests.

These are written from the shape of actual GTA sales listings: the MLM ones
mirror how Primerica and Cydcor-style ads are genuinely worded, and the good
ones mirror how a real SaaS AE posting reads. Anything that trips a filter
should look like something you'd actually see, not like a keyword soup.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from salesradar.models import Job


def hours_ago(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def make_job(**overrides) -> Job:
    """A clean, fully-qualifying Toronto AE posting. Override to break it."""
    defaults = dict(
        source="adzuna",
        source_id="test-1",
        title="Account Executive",
        company="Northbound Software Inc.",
        location="Toronto, ON",
        url="https://example.com/jobs/1",
        description=(
            "We're hiring an Account Executive for our Toronto office. "
            "Base salary of $70,000 plus uncapped commission, OTE $120,000. "
            "You'll own the full cycle for mid-market accounts in Ontario. "
            "3+ years of B2B SaaS closing experience required."
        ),
        salary_min=70000.0,
        salary_max=120000.0,
        posted_at=hours_ago(3),
        latitude=43.6532,
        longitude=-79.3832,
    )
    defaults.update(overrides)
    return Job(**defaults)


# --- should be REJECTED by the commission filter ----------------------------

COMMISSION_ONLY = make_job(
    source_id="mlm-1",
    title="Sales Representative",
    company="Apex Marketing Group",
    description=(
        "100% commission only position. Unlimited earning potential! "
        "You are an independent contractor (1099) and own your own business. "
        "No cap on what you can make. Start immediately."
    ),
    salary_min=None,
    salary_max=None,
)

PRIMERICA = make_job(
    source_id="mlm-2",
    title="Business Development Representative",
    company="Primerica Financial Services",
    description=(
        "Join our Toronto team as a licensed financial representative. "
        "Build your own agency. Be your own boss. Commission based earnings."
    ),
    salary_min=None,
    salary_max=None,
)

CYDCOR_STYLE = make_job(
    source_id="mlm-3",
    title="Sales Representative — Entry Level",
    company="Summit Acquisitions (Cydcor affiliate)",
    description=(
        "No experience necessary! Earn $100k in your first year. "
        "Weekly pay. Full training provided. Face to face sales."
    ),
    salary_min=None,
    salary_max=None,
)

HYPE_NO_SALARY = make_job(
    source_id="mlm-4",
    title="Inside Sales Representative",
    company="Meridian Group",
    description=(
        "Unlimited earning potential for the right candidate. "
        "Fast-paced environment, growing team, great culture."
    ),
    salary_min=None,
    salary_max=None,
)

# --- should be UNCERTAIN (conflicting signals) ------------------------------

CONFLICTING_SIGNALS = make_job(
    source_id="uncertain-1",
    title="Account Executive",
    company="Halcyon Media",
    description=(
        "Base salary plus uncapped commission. This is a 1099 independent "
        "contractor engagement with a guaranteed base of $45,000 for the "
        "first six months."
    ),
    salary_min=45000.0,
    salary_max=None,
)

# --- should be ACCEPTED by the commission filter ----------------------------

BASE_PLUS_COMMISSION = make_job(
    source_id="good-1",
    title="Account Executive",
    company="Riverstone Technologies",
    description=(
        "Base + commission structure. $65,000 base with an OTE of $130,000. "
        "Uncapped commission on everything above quota."
    ),
    salary_min=65000.0,
)

SALARY_ONLY_NO_PHRASE = make_job(
    source_id="good-2",
    title="Sales Development Representative",
    company="Cardinal Analytics",
    description="Join our SDR team in downtown Toronto. Strong benefits.",
    salary_min=58000.0,
)

LOW_SALARY_NO_FLAGS = make_job(
    source_id="edge-1",
    title="Inside Sales Representative",
    company="Bayview Distributors",
    description="Inside sales role supporting our Ontario dealer network.",
    salary_min=32000.0,
)

# --- geography --------------------------------------------------------------

VAUGHAN_JOB = make_job(
    source_id="geo-1",
    title="Business Development Manager",
    company="Concord Industrial",
    location="Vaughan, ON",
    latitude=43.8361,
    longitude=-79.4983,
)

OTTAWA_JOB = make_job(
    source_id="geo-2",
    location="Ottawa, ON",
    latitude=45.4215,
    longitude=-75.6972,
)

CHICAGO_JOB = make_job(
    source_id="geo-3",
    location="Chicago, IL, United States",
    latitude=41.8781,
    longitude=-87.6298,
)

REMOTE_US = make_job(
    source_id="geo-4",
    location="Remote - US",
    latitude=None,
    longitude=None,
)

REMOTE_ONTARIO = make_job(
    source_id="geo-5",
    location="Remote",
    description="Remote role open to candidates in the Greater Toronto Area.",
    latitude=None,
    longitude=None,
)

REMOTE_NOWHERE = make_job(
    source_id="geo-6",
    location="Remote",
    description="Fully remote sales role. Work from anywhere.",
    latitude=None,
    longitude=None,
)

MISSISSAUGA_NO_COORDS = make_job(
    source_id="geo-7",
    source="indeed_email",
    location="Mississauga, ON",
    latitude=None,
    longitude=None,
)

BARRIE_EDGE = make_job(
    source_id="geo-8",
    location="Barrie, ON",
    latitude=44.3894,
    longitude=-79.6903,
)

# --- titles -----------------------------------------------------------------

RETAIL_FLOOR = make_job(
    source_id="title-1",
    title="Retail Sales Associate",
    company="Fairview Mall Electronics",
)

AUTOMOTIVE = make_job(
    source_id="title-2",
    title="Automotive Sales Representative",
    company="Downtown Toyota",
)

SALES_ENGINEER_PENG = make_job(
    source_id="title-3",
    title="Sales Engineer",
    company="Precision Controls Ltd.",
    description=(
        "Base salary $95,000. Must hold a P.Eng licence in Ontario and have "
        "5 years of industrial automation experience."
    ),
    salary_min=95000.0,
)

SALES_ENGINEER_NO_PENG = make_job(
    source_id="title-4",
    title="Sales Engineer",
    company="Cloudline Systems",
    description=(
        "Technical pre-sales role. Base salary $90,000 plus commission. "
        "CS degree or equivalent experience."
    ),
    salary_min=90000.0,
)

SDR = make_job(source_id="title-5", title="SDR - Outbound", company="Loop Health")
BDR = make_job(source_id="title-6", title="BDR, Enterprise", company="Northwind")
ACCOUNT_MANAGER = make_job(
    source_id="title-7", title="Account Manager", company="Kestrel Logistics"
)
IRRELEVANT = make_job(
    source_id="title-8", title="Warehouse Supervisor", company="Kestrel Logistics"
)

# --- freshness --------------------------------------------------------------

STALE = make_job(source_id="fresh-1", posted_at=hours_ago(48))
FRESH = make_job(source_id="fresh-2", posted_at=hours_ago(2))
NO_DATE = make_job(source_id="fresh-3", posted_at=None)
BORDERLINE = make_job(source_id="fresh-4", posted_at=hours_ago(23.5))
