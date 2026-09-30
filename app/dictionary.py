"""Standard data dictionary.

Every show's registration export is mapped onto the same canonical fields so
LEX (Europe), LNA (North America) and LME (Middle East) can be compared like
for like. Raw column names differ by show and year (e.g. "26_LEM_Annual Budget",
"27_LNA_Annual Budget"), so questions are matched on the text after the
year/show prefix.
"""
import re

# ---------------------------------------------------------------------------
# Canonical fields: what each one means, shown on the Data Dictionary tab.
# ---------------------------------------------------------------------------
FIELDS = [
    ("source_id", "Registration ID", "Unique ID from the registration platform (e.g. Visitor Code)."),
    ("created_at", "Registration date", "When the registration was created (UTC)."),
    ("category", "Audience category", "Attendee (visitor / VIP / speaker / delegate), Exhibitor, Press, Staff or Organiser. Attendee is the customer audience."),
    ("reg_type_raw", "Registration type (raw)", "The show's own label - Visitor, Delegate, VIP, etc."),
    ("company", "Company", "Company name as entered."),
    ("country", "Country", "ISO-style country name."),
    ("world_region", "World region", "Continent / trading region derived from country."),
    ("job_title", "Job title", "Free-text job title."),
    ("job_function", "Job function", "Standard function picklist (Sales, R&D, Procurement...)."),
    ("seniority", "Seniority", "Derived from job title: Executive / Owner, Director / VP / Head, Manager, Professional, Student / Academic, Unclassified."),
    ("industry", "Industry", "Main business activity picklist."),
    ("industry_group", "Industry group", "Lubricant supply chain, End-user industry, or Services & other."),
    ("buyer_supplier", "Buyer / supplier", "Self-declared business opportunity."),
    ("budget_responsibility", "Purchasing influence", "Yes (budget holder), Influence, or No."),
    ("budget_band", "Annual budget", "Normalised annual purchasing budget band."),
    ("products", "Product interests", "Pipe-separated list of products of interest."),
    ("commercial_interest", "Commercial interest", "Also interested in Exhibiting / Sponsoring / Other."),
    ("attended", "Attended", "Badge scanned onsite. Blank until the attendance feed is connected."),
    ("previous_attendee", "Previous attendee", "Attended the previous edition. Blank until the CRM or history feed is connected."),
    ("source_channel", "Registration source", "UTM / promo code / channel. Blank until captured."),
]

# ---------------------------------------------------------------------------
# Raw column -> canonical field. Keys are lower-cased; question columns are
# matched after stripping a "26_LEM_" style prefix.
# ---------------------------------------------------------------------------
COLUMN_ALIASES = {
    "source_id": ["visitor code", "registration id", "attendee id", "delegate id", "badge id", "id"],
    "created_at": ["create time (utc)", "create time", "registration date", "created at", "created"],
    "reg_type_raw": ["registration type", "attendee type", "delegate type", "badge type", "type"],
    "first_name": ["first name", "firstname"],
    "last_name": ["last name", "lastname", "surname"],
    "company": ["company", "company name", "organisation", "organization"],
    "email": ["email", "email address"],
    "city": ["city", "town"],
    "state": ["state", "county", "province"],
    "country": ["country"],
    "job_title": ["job function", "job title", "title", "position"],
    "job_function": ["what is your job function?", "job function (picklist)"],
    "industry": ["what is your main business activity?", "main business activity", "industry"],
    "buyer_supplier": ["what is your business opportunity / category?", "buyer or supplier"],
    "budget_band": ["annual budget"],
    "budget_responsibility": ["budgetary responsibility?", "budgetary responsibility"],
    "products": ["which products are you interested in?", "products of interest"],
    "commercial_interest": ["would you also be interested in the following?"],
    "attended": ["attended", "attendance", "checked in", "badge scanned", "scanned"],
    "previous_attendee": ["previous attendee", "attended previous year", "returning"],
    "source_channel": ["registration source", "source", "utm source", "promo code", "promotion code"],
}

_PREFIX = re.compile(r"^\d{2}_[A-Za-z]+_")


def canonical_column(raw):
    key = _PREFIX.sub("", str(raw).strip()).lower()
    for field, aliases in COLUMN_ALIASES.items():
        if key in aliases:
            return field
    return None


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------
def clean(v):
    if v is None:
        return None
    s = str(v).replace("\xa0", " ").strip()
    if not s or s.lower() in ("nan", "nat", "none", "null"):
        return None
    return s


CATEGORY_RULES = [
    ("Exhibitor", ("exhibitor", "exhibitor staff", "booth")),
    ("Press", ("press", "media", "journalist")),
    ("Staff", ("staff", "contractor", "crew")),
    ("Organiser", ("organiser", "organizer", "host")),
    ("Attendee", ("visitor", "vip", "speaker", "delegate", "attendee", "guest", "buyer")),
]


def category(reg_type):
    t = (reg_type or "").lower()
    for cat, keys in CATEGORY_RULES:
        if any(t.startswith(k) for k in keys):
            return cat
    return "Other"


BUDGET_BANDS = [  # (canonical label, sort order, matcher on the raw text)
    ("$1k-10k", 1, r"\$1000 - \$10000"),
    ("$10k-50k", 2, r"\$10001 - \$50000"),
    # The form text reads "$50001 - $10000"; the intended band is $50k-$100k.
    ("$50k-100k", 3, r"\$50001 - \$100?000"),
    # The form text reads "$10001 - $250000"; the intended band is $100k-$250k.
    ("$100k-250k", 4, r"\$100?001 - \$250000"),
    ("$250k-500k", 5, r"\$250001 - \$500000"),
    ("$500k-1M", 6, r"\$500001 - \$1 million"),
    ("Over $1M", 7, r">\s*\$1 million"),
]
BUDGET_ORDER = [b[0] for b in BUDGET_BANDS]


def budget_band(raw):
    s = clean(raw)
    if not s:
        return None
    for label, _, pat in BUDGET_BANDS:
        if re.search(pat, s):
            return label
    return s


def budget_responsibility(raw):
    s = (clean(raw) or "").lower()
    if s.startswith("yes"):
        return "Yes"
    if s.startswith("infl"):
        return "Influence"
    if s.startswith("no"):
        return "No"
    return None


def buyer_supplier(raw):
    s = (clean(raw) or "").lower()
    if "buy" in s:
        return "Buyer"
    if "suppl" in s or "sell" in s:
        return "Supplier"
    return None


def yes_no(raw):
    s = (clean(raw) or "").lower()
    if s in ("y", "yes", "true", "1", "attended", "scanned", "checked in"):
        return True
    if s in ("n", "no", "false", "0", "no show", "not attended"):
        return False
    return None


# Seniority from free-text job title. Order matters: VP before President,
# Managing Director before Director.
SENIORITY_ORDER = ["Executive / Owner", "Director / VP / Head", "Manager",
                   "Professional", "Student / Academic", "Unclassified"]
SENIOR_LEVELS = SENIORITY_ORDER[:2]
_SEN = [
    ("Director / VP / Head", r"\b(vp|svp|evp|vice[- ]president|vice[- ]presidente)\b"),
    ("Executive / Owner", r"\b(ceo|cfo|coo|cto|cco|cmo|cso|chief|owner|founder|co-founder|"
                          r"president|chairman|chairwoman|managing director|md|general manager|gm|"
                          r"partner|proprietor|gesch[aä]ftsf[uü]hrer|directeur g[eé]n[eé]ral|"
                          r"director general|gerente general|country manager|executive director)\b"),
    ("Director / VP / Head", r"\b(director|directeur|direktor|directora?|head|leiter|leader of)\b"),
    ("Manager", r"\b(manager|mgr|supervisor|team lead|lead|responsable|gerente|superintendent|"
                r"coordinator|principal)\b"),
    ("Student / Academic", r"\b(student|professor|phd|intern|lecturer|academic|postdoc)\b"),
    ("Professional", r"\b(engineer|specialist|chemist|scientist|analyst|consultant|technician|"
                     r"researcher|advisor|adviser|officer|executive|representative|expert|"
                     r"tribologist|technologist|developer|buyer|purchaser|sales|account|"
                     r"assistant|associate|agent|formulator|operator|marketing|planner)\b"),
]
_SEN = [(lvl, re.compile(p, re.I)) for lvl, p in _SEN]


def seniority(title, job_function=None):
    t = clean(title) or ""
    for lvl, pat in _SEN:
        if pat.search(t):
            return lvl
    jf = (clean(job_function) or "").lower()
    if jf.startswith("owner/ceo"):
        return "Executive / Owner"
    if jf.startswith("student") or jf.startswith("scientist/professor"):
        return "Student / Academic"
    return "Unclassified"


SUPPLY_CHAIN = {
    "Additives", "Base Oils", "Lubricant Manufacturer", "Distribution / Aftermarket",
    "Equipment Supplier to the Lubricant Industry", "Lubrication Technology",
    "Chemicals (End User)", "Logistics & Warehousing",
}
SERVICES = {
    "Engineering Services", "Lubrication Engineering Services", "Lab Services",
    "Testing & Certification", "Academic & Research", "Other",
}


def industry_group(ind):
    if not ind:
        return None
    if ind in SUPPLY_CHAIN:
        return "Lubricant supply chain"
    if ind in SERVICES:
        return "Services & other"
    return "End-user industry"


COUNTRY_ALIASES = {
    "turkey": "Türkiye", "usa": "United States", "us": "United States",
    "united states of america": "United States", "uk": "United Kingdom",
    "great britain": "United Kingdom", "england": "United Kingdom", "uae": "United Arab Emirates",
    "iran, islamic republic of": "Iran", "korea, republic of": "South Korea",
    "russian federation": "Russia", "viet nam": "Vietnam", "czechia": "Czech Republic",
    "moldova, republic of": "Moldova", "tanzania, united republic of": "Tanzania",
    "venezuela, bolivarian republic of": "Venezuela", "syrian arab republic": "Syria",
    "palestine, state of": "Palestine", "brunei darussalam": "Brunei",
}


_LEGAL = re.compile(r"\b(gmbh|ag|se|kg|co|ltd|limited|inc|llc|bv|b\.v|nv|n\.v|spa|s\.p\.a|sa|s\.a|sas|srl|"
                    r"s\.r\.l|plc|corp|corporation|company|oy|ab|as|a/s|pvt|pte|fze|fzco|llp|sarl|kft|sp z o\.o)\b\.?")


def company_key(name):
    """Grouping key so 'BASF SE' and 'BASF' count as one company."""
    s = (clean(name) or "").lower().replace("&", " ")
    s = _LEGAL.sub(" ", s)
    s = re.sub(r"[^\w]+", " ", s).strip()
    return s or None


def country(raw):
    s = clean(raw)
    if not s:
        return None
    return COUNTRY_ALIASES.get(s.lower(), s)


_REGIONS = {
    "Western Europe": ["Germany", "Netherlands", "Belgium", "France", "Luxembourg", "Switzerland",
                       "Austria", "Ireland", "United Kingdom", "Monaco", "Liechtenstein"],
    "Southern Europe": ["Italy", "Spain", "Portugal", "Greece", "Malta", "Cyprus", "North Macedonia",
                        "Albania", "Serbia", "Montenegro", "Kosovo", "Croatia", "Slovenia",
                        "Bosnia and Herzegovina"],
    "Northern Europe": ["Denmark", "Sweden", "Norway", "Finland", "Iceland", "Estonia", "Latvia",
                        "Lithuania", "Greenland"],
    "Eastern Europe": ["Poland", "Czech Republic", "Slovakia", "Hungary", "Romania", "Bulgaria",
                       "Ukraine", "Moldova", "Belarus", "Russia", "Georgia", "Armenia", "Azerbaijan"],
    "Türkiye & Central Asia": ["Türkiye", "Kazakhstan", "Uzbekistan", "Turkmenistan", "Kyrgyzstan",
                               "Tajikistan", "Afghanistan"],
    "Middle East": ["United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman",
                    "Iran", "Iraq", "Israel", "Jordan", "Lebanon", "Syria", "Yemen", "Palestine"],
    "Africa": ["Egypt", "Morocco", "Algeria", "Tunisia", "Libya", "Nigeria", "Ghana", "Kenya",
               "South Africa", "Ethiopia", "Tanzania", "Uganda", "Rwanda", "Burundi", "Cameroon",
               "Senegal", "Mali", "Niger", "Burkina Faso", "Benin", "Togo", "Guinea", "Mauritania",
               "Angola", "Zambia", "South Sudan", "Zimbabwe", "Mozambique", "Côte d'Ivoire", "Sudan"],
    "South Asia": ["India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal",
                   "British Indian Ocean Territory"],
    "East & Southeast Asia": ["China", "Japan", "South Korea", "Hong Kong", "Taiwan", "Singapore",
                              "Malaysia", "Thailand", "Indonesia", "Vietnam", "Philippines", "Brunei"],
    "North America": ["United States", "Canada", "Mexico", "United States Minor Outlying Islands", "Guam"],
    "Latin America": ["Brazil", "Argentina", "Chile", "Colombia", "Peru", "Ecuador", "Venezuela",
                      "Guyana", "Guadeloupe", "Uruguay", "Paraguay", "Bolivia", "Costa Rica", "Panama"],
    "Oceania": ["Australia", "New Zealand"],
}
REGION_OF = {c: r for r, names in _REGIONS.items() for c in names}


def world_region(c):
    return REGION_OF.get(c or "", "Other / unknown") if c else None


# Sources the proposal wants joined up. Status is shown on the Data Sources tab.
DATA_SOURCES = [
    ("Registration platform", "Who registered, profile answers, timing", "connected"),
    ("Onsite badge scans", "Attended vs registered-but-didn't-attend", "planned"),
    ("CRM", "Previous attendance, exhibitor / sponsor history, company size", "planned"),
    ("Dotdigital", "Email opens and clicks by contact", "planned"),
    ("GA4", "Website visits, content viewed, traffic source", "planned"),
    ("LinkedIn / paid media", "First touch, campaign attribution", "planned"),
    ("Show app", "Onsite engagement, sessions, meetings", "planned"),
    ("Survey platform", "Satisfaction, reasons for not attending", "planned"),
    ("Sales data", "Returned as exhibitor / sponsor", "planned"),
]
