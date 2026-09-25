"""Sector profiles.

Everything that differs between one kind of livelihood and another lives here,
so the checks in checks.py stay the same for a vegetable plot, a grocery shop,
a tailoring unit or a three-wheeler.

To add a sector, copy a SECTOR entry and edit it. No other file changes.
Each profile carries:

  detect            words that identify the sector in the proposal text
  specificity       what a specific overview must contain (weights total 5)
  market_terms      evidence of a real market
  sales_basis       evidence that sales were built up, not guessed
  growth_drivers    reasons that justify a jump in sales
  input_keys        annual cost rows that must rise with production
  margin_ok/limit   profit/sales bands that need no evidence / are implausible
  growth_*          year-1 sales growth bands for this kind of business
  risks             risk categories, and which ones a proposal must cover
  equipment         item vocabulary, so the tool can match request to list
  need_signals      what in the text justifies each item
  compliance        licences, permits and insurance the business needs
  training_terms    what counts as technical training here
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# vocabulary shared by every sector
# --------------------------------------------------------------------------
COMMON_EQUIPMENT = {
    "tools": ["tool", "tool kit", "hand tools", "mammoty", "hoe"],
    "storage": ["storage", "rack", "shelf", "shelves", "cupboard", "almirah", "container", "barrel"],
    "table": ["table", "work bench", "workbench", "counter"],
    "chair": ["chair", "stool", "bench"],
    "scale": ["scale", "weighing", "balance"],
    "generator": ["generator", "inverter", "solar panel", "battery"],
    "phone": ["phone", "smart phone", "mobile"],
    "computer": ["computer", "laptop", "printer", "pos", "billing machine"],
    "cart": ["cart", "trolley", "push cart", "bicycle", "trishaw"],
    "shed": ["shed", "roof", "building", "cabin", "stall", "kiosk"],
}

COMMON_RISKS = {
    "market price or demand": r"price|market|demand|buyer|customer|competit|season(al)? (drop|demand)",
    "equipment failure": r"equipment|machine|breakdown|repair|maintenance|motor|vehicle",
    "health or labour": r"health|illness|sick|injur|labou?r shortage|accident",
    "theft or damage": r"theft|steal|rob|fire|damage|loss of stock",
}

COMMON_NEED_SIGNALS = {
    "generator": r"power ?cut|electricity|current|outage|solar",
    "storage": r"storage|store|space|damage|spoil",
    "computer": r"record|bill|account|order|design",
    "phone": r"order|customer call|whatsapp|online",
    "cart": r"deliver|transport|carry|door to door|mobile",
    "shed": r"rain|sun|space|premises|shelter",
}

EXPERIENCE = r"\b\d+\s*(years?|months?)\b(?!\s*old)"

BUSINESS_TRAINING = (r"book ?keeping|record|financial|business|marketing|saving|costing|"
                     r"entrepreneur|pricing|customer (care|service)|digital|social media")


@dataclass
class Sector:
    id: str
    name: str
    detect: str
    specificity: list[tuple[str, str, float]]
    market_terms: str
    sales_basis: str
    growth_drivers: str
    input_keys: list[str]
    margin_ok: float
    margin_limit: float
    growth_ok: float
    growth_caution: float
    growth_limit: float
    risks: dict[str, str] = field(default_factory=dict)
    must_cover: list[str] = field(default_factory=list)
    equipment: dict[str, list[str]] = field(default_factory=dict)
    need_signals: dict[str, str] = field(default_factory=dict)
    compliance: list[tuple[str, str]] = field(default_factory=list)
    training_terms: str = r"technical|production|skill|quality"
    unit_hint: str = "unit"

    # -------------------------------------------------------------- helpers
    def all_equipment(self) -> dict[str, list[str]]:
        return {**COMMON_EQUIPMENT, **self.equipment}

    def all_risks(self) -> dict[str, str]:
        return {**COMMON_RISKS, **self.risks}

    def all_need_signals(self) -> dict[str, str]:
        return {**COMMON_NEED_SIGNALS, **self.need_signals}

    def nouns_in(self, text: str) -> set[str]:
        t = (text or "").lower()
        return {k for k, syns in self.all_equipment().items() if any(s in t for s in syns)}


SECTORS: dict[str, Sector] = {}


def _add(s: Sector) -> Sector:
    SECTORS[s.id] = s
    return s


# --------------------------------------------------------------------------
# 1. crop agriculture
# --------------------------------------------------------------------------
_add(Sector(
    id="crop", name="Crop cultivation",
    detect=(r"cultivat|vegetable|paddy|crop|farm(ing|er)?|carrot|leek|cabbage|potato|beans|beetroot|"
            r"tomato|chilli|brinjal|okra|onion|garlic|banana|fruit|tea|nurser|floricultur|flower|"
            r"mushroom|home garden|agricultur"),
    specificity=[
        ("crops named", r"\b(carrot|leeks?|cabbage|potato|beans?|beetroot|radish|knol ?khol|lettuce|"
                        r"cauliflower|broccoli|tomato|capsicum|strawberr\w*|pepper|pumpkin|onion|garlic|"
                        r"chilli|brinjal|okra|cucumber|paddy|tea|banana|papaya|mushroom|flower|anthurium)\b", 1.5),
        ("land extent", r"\b(acres?|perch(es)?|hectares?|\bha\b)\b", 1.5),
        ("years of experience", EXPERIENCE, 1.0),
        ("season or yield detail", r"\b(kg|yield|harvest|season|maha|yala|per plant|per bed)\b", 1.0),
    ],
    market_terms=(r"buyer|collector|wholesale|economic cent(er|re)|dedicated economic|supermarket|"
                  r"cargills|keells|contract|middleman|pola\b|fair|per kg|/kg|farm ?gate"),
    sales_basis=r"(\bkg\b|yield|price per|per kg|harvests? per|per season|per plant|per bed)",
    growth_drivers=(r"extend|expan|additional land|new land|more land|acre|perch|yield|irrigat|"
                    r"second season|two seasons|reduce (loss|damage)|green ?house|poly ?tunnel"),
    input_keys=["seeds", "fertilizer", "chemicals", "raw_material", "purchases"],
    margin_ok=0.45, margin_limit=0.60,
    growth_ok=0.25, growth_caution=0.50, growth_limit=0.80,
    risks={"weather": r"flood|drought|rain|frost|landslide|weather|climat|wind",
           "pest or disease": r"pest|disease|insect|fung|blight|worm",
           "wildlife": r"wild|animal|boar|monkey|porcupine|elephant|stray|cattle",
           "soil or water": r"soil|fertility|water|irrigation|well|drought"},
    must_cover=["market price or demand", "weather", "wildlife", "pest or disease"],
    equipment={"spray": ["spray", "sprayer", "spary", "knapsack"],
               "hose": ["hose", "pipe", "tube"],
               "motor": ["motor", "pump", "water pump"],
               "fence": ["fence", "fencing", "net fence"],
               "tank": ["tank", "water tank"],
               "sprinkler": ["sprinkler", "drip", "irrigation"],
               "tiller": ["tiller", "tractor", "plough", "weeder"],
               "polytunnel": ["polytunnel", "poly tunnel", "green house", "greenhouse", "net house"],
               "seeds": ["seed", "seedling", "plant material", "sapling"]},
    need_signals={"fence": r"wild|animal|boar|monkey|porcupine|elephant|theft|stray|cattle",
                  "hose": r"water|irrigat|dry|drought|by hand",
                  "motor": r"water|irrigat|well|dry|drought",
                  "sprinkler": r"water|irrigat|labou?r|time",
                  "spray": r"pest|disease|weed|fung",
                  "polytunnel": r"rain|frost|pest|quality|off ?season",
                  "tank": r"water|store|dry|drought",
                  "tiller": r"land prepar|plough|labou?r|hire"},
    compliance=[],
    training_terms=r"technical|cultivation|production|farming|gap|agronom|nursery|compost|ipm",
    unit_hint="kg",
))

# --------------------------------------------------------------------------
# 2. livestock
# --------------------------------------------------------------------------
_add(Sector(
    id="livestock", name="Livestock and animal husbandry",
    detect=(r"livestock|dairy|cattle|cow|buffalo|goat|sheep|poultry|chicken|broiler|layer|egg|duck|"
            r"piggery|pig|rabbit|bee ?keep|apiar|honey|animal husbandry|calf|heifer"),
    specificity=[
        ("animals or birds and numbers", r"\b\d+\s*(cows?|cattle|goats?|birds?|chicks?|hens?|layers?|"
                                         r"broilers?|pigs?|ducks?|rabbits?|hives?|boxes)\b", 1.5),
        ("production rate", r"\b(litre|liter|l/day|eggs? per|per day|per month|kg of (milk|honey|meat)|"
                            r"milk yield|laying)\b", 1.5),
        ("housing or land", r"\b(shed|cage|coop|pen|sty|hive|barn|stall|acres?|perch(es)?)\b", 1.0),
        ("years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=(r"collector|milk (board|collect)|milco|nestl|dairy|hatcher|wholesale|shop|hotel|bakery|"
                  r"restaurant|per litre|per egg|per kg|/l\b|buyer|contract"),
    sales_basis=r"\b(litre|eggs?|kg|per day|per month|per bird|per cow|cycle|batch)\b",
    growth_drivers=(r"more (animals|birds|cows|goats)|additional (animal|bird|cow|shed)|expand|extra batch|"
                    r"increase (herd|flock)|better feed|improved breed|artificial insemination|vaccinat"),
    input_keys=["feed", "veterinary", "raw_material", "purchases"],
    margin_ok=0.35, margin_limit=0.50,
    growth_ok=0.25, growth_caution=0.50, growth_limit=1.00,
    risks={"animal disease": r"disease|infection|mortality|death|epidemic|newcastle|mastitis|vaccinat",
           "feed cost or supply": r"feed|fodder|grass|maize|ration|price of feed",
           "weather": r"flood|drought|heat|rain|weather|climat",
           "predators or theft": r"predator|dog|mongoose|snake|wild|theft"},
    must_cover=["animal disease", "market price or demand", "feed cost or supply", "equipment failure"],
    equipment={"shed": ["shed", "coop", "cage", "pen", "sty", "housing", "barn"],
               "feeder": ["feeder", "drinker", "waterer", "trough"],
               "milk_can": ["milk can", "milking", "milk churn", "bucket"],
               "chiller": ["chiller", "cooler", "cold", "fridge", "freezer"],
               "brooder": ["brooder", "incubator", "heater", "bulb"],
               "hive": ["hive", "bee box", "honey extractor"],
               "animals": ["cow", "cattle", "goat", "chick", "bird", "pig", "calf", "layer", "broiler"],
               "feed": ["feed", "fodder", "ration", "concentrate"],
               "chopper": ["chopper", "grass cutter", "shredder"]},
    need_signals={"shed": r"space|shelter|rain|expand|more (animals|birds)|disease",
                  "chiller": r"milk|spoil|cold|quality|transport",
                  "brooder": r"chick|mortality|cold|hatch",
                  "feeder": r"feed|waste|labou?r|hygien",
                  "chopper": r"fodder|grass|labou?r|time",
                  "milk_can": r"milk|collect|transport|hygien"},
    compliance=[("veterinary registration or vaccination plan", r"vaccinat|veterinar|livestock (officer|development)|vs office"),
                ("local authority approval for the shed", r"local authority|pradeshiya|municipal|approval|permit")],
    training_terms=r"technical|animal|husbandry|rearing|feeding|breeding|veterinar|hygien|milk|poultry",
    unit_hint="litre or bird",
))

# --------------------------------------------------------------------------
# 3. fisheries
# --------------------------------------------------------------------------
_add(Sector(
    id="fisheries", name="Fisheries and aquaculture",
    detect=r"fisher|fishing|fish|prawn|shrimp|crab|ornamental fish|aquacult|dried fish|boat|lagoon|tank fish",
    specificity=[
        ("craft and gear", r"\b(boat|canoe|oru|net|gill ?net|trap|line|tank|pond|engine)\b", 1.5),
        ("catch or stocking volume", r"\b(kg|catch|per trip|per day|fingerling|stock(ing)?|per month)\b", 1.5),
        ("fishing area or season", r"\b(lagoon|reservoir|tank|sea|river|season|monsoon|inland)\b", 1.0),
        ("years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=r"collector|fish market|wholesale|hotel|restaurant|export|per kg|/kg|buyer|auction|aquarium shop",
    sales_basis=r"\b(kg|per trip|per day|catch|fingerling|per month)\b",
    growth_drivers=r"more (trips|nets|tanks)|additional (net|tank|pond)|engine|expand|stocking|preserve|ice",
    input_keys=["raw_material", "purchases", "feed", "fuel"],
    margin_ok=0.45, margin_limit=0.60,
    growth_ok=0.25, growth_caution=0.50, growth_limit=0.80,
    risks={"weather or sea conditions": r"weather|monsoon|storm|rain|flood|drought|water level",
           "catch or stock failure": r"catch|stock|mortality|disease|pollution|low season",
           "fuel or input cost": r"fuel|kerosene|petrol|diesel|ice|feed"},
    must_cover=["weather or sea conditions", "market price or demand", "equipment failure", "catch or stock failure"],
    equipment={"boat": ["boat", "canoe", "oru", "craft"],
               "engine": ["engine", "outboard", "motor"],
               "net": ["net", "gill net", "trap", "line", "hook"],
               "tank": ["tank", "pond", "aquarium", "cage"],
               "cooler": ["cooler", "ice box", "insulated", "freezer", "chiller"],
               "aerator": ["aerator", "pump", "filter"],
               "fingerlings": ["fingerling", "fry", "seed fish", "post larvae"]},
    need_signals={"cooler": r"spoil|ice|fresh|quality|price",
                  "engine": r"distance|time|trip|fuel",
                  "net": r"catch|damage|old net|torn",
                  "aerator": r"oxygen|mortality|density|water quality"},
    compliance=[("boat registration or fishing licence", r"licen[cs]e|registration|fisheries (department|inspector)|permit")],
    training_terms=r"technical|fish|aquacult|net|handling|hygien|breeding|post ?harvest",
    unit_hint="kg",
))

# --------------------------------------------------------------------------
# 4. food processing
# --------------------------------------------------------------------------
_add(Sector(
    id="food", name="Food processing and catering",
    detect=(r"bakery|bake|cake|short ?eat|sweet|catering|canteen|food processing|spice|grind|curry powder|"
            r"papadam|pickle|jam|cordial|yoghurt|curd|ice cream|rice mill|flour|packing|snack|juice|"
            r"hopper|kottu|lunch packet|tea shop|restaurant|hotel"),
    specificity=[
        ("products named", r"\b(bread|bun|cake|biscuit|short ?eat|roti|hopper|string hopper|rice|curry|"
                           r"lunch packet|curry powder|chilli powder|pickle|jam|cordial|yoghurt|curd|"
                           r"ice cream|juice|snack|papadam|sweets?)\b", 1.5),
        ("production per batch or day", r"\b(per day|per batch|per month|packets?|kg|litres?|units?|pieces?|"
                                        r"loaves|portions?)\b", 1.5),
        ("premises or kitchen", r"\b(kitchen|premises|shop|oven|stall|home|room|space|outlet)\b", 1.0),
        ("years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=(r"shop|retail|wholesale|hotel|canteen|school|office|order|super ?market|boutique|"
                  r"per packet|per kg|customers? per day|delivery|regular order"),
    sales_basis=r"\b(per day|per batch|packets?|pieces?|kg|units?|orders?|customers? per day)\b",
    growth_drivers=(r"more (orders|outlets|production)|new product|extra batch|packaging|delivery|shelf life|"
                    r"expand|oven|machine|display|regular order"),
    input_keys=["ingredients", "raw_material", "purchases", "packaging", "fuel"],
    margin_ok=0.35, margin_limit=0.50,
    growth_ok=0.30, growth_caution=0.60, growth_limit=1.00,
    risks={"ingredient price or supply": r"ingredient|raw material|flour|sugar|price|supply|import",
           "spoilage or quality": r"spoil|expire|shelf life|quality|hygien|contaminat",
           "fuel or power": r"gas|fuel|power ?cut|electricity|firewood"},
    must_cover=["market price or demand", "ingredient price or supply", "spoilage or quality", "equipment failure"],
    equipment={"oven": ["oven", "bakery oven", "gas cooker", "cooker", "stove", "fryer"],
               "mixer": ["mixer", "mixing", "dough", "blender", "grinder", "mill"],
               "fridge": ["fridge", "refrigerator", "freezer", "chiller", "cooler"],
               "sealer": ["sealer", "sealing", "packing machine", "packaging"],
               "utensils": ["utensil", "pan", "pot", "tray", "mould", "vessel", "bowl"],
               "display": ["display", "showcase", "cabinet", "rack"],
               "gas": ["gas", "cylinder", "firewood", "burner"]},
    need_signals={"oven": r"bake|batch|quantity|time|quality|demand",
                  "mixer": r"by hand|labou?r|time|quantity|consistent",
                  "fridge": r"spoil|fresh|cold|store|drinks|milk",
                  "sealer": r"packag|shelf life|hygien|brand|label",
                  "display": r"customer|shop|attract|sell"},
    compliance=[("public health (PHI) approval or food handling certificate", r"phi|public health|food handling|medical (certificate|report)|health certificate"),
                ("local authority trade licence", r"trade licen[cs]e|business (registration|licen[cs]e)|pradeshiya|municipal|urban council"),
                ("labelling for packed food", r"label|expiry|batch (number|code)|sldb|sri lanka standard|sls")],
    training_terms=r"technical|food|hygien|bak|cook|catering|processing|packaging|quality|haccp|gmp",
    unit_hint="packet",
))

# --------------------------------------------------------------------------
# 5. retail trade
# --------------------------------------------------------------------------
_add(Sector(
    id="retail", name="Retail and trading",
    detect=(r"grocer|boutique|retail|shop|trading|trader|vend|stall|kiosk|pola|mobile shop|cool ?spot|"
            r"communication|pharmac|stationery|hardware|textile|second hand|whole ?sale|resell|buy and sell"),
    specificity=[
        ("range of goods", r"\b(grocer|rice|dhal|vegetable|fruit|stationery|textile|garment|hardware|"
                           r"cosmetic|spare parts?|mobile|phone|drinks|snack|items?|goods|stock)\b", 1.5),
        ("location and customers", r"\b(junction|road|town|village|school|bus stand|market|footfall|"
                                   r"customers? per day|walk[- ]?in|regular customers)\b", 1.5),
        ("turnover or margin detail", r"\b(daily sales|per day|turnover|margin|mark ?up|profit per|"
                                      r"stock value|per month)\b", 1.0),
        ("years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=(r"customers? per day|walk[- ]?in|regular customer|village|town|junction|school|"
                  r"competit|supplier|whole ?sale|credit sale|delivery|margin|mark ?up"),
    sales_basis=r"\b(per day|daily sales|customers? per day|turnover|margin|mark ?up|stock|per month)\b",
    growth_drivers=(r"more stock|wider range|new items|add (drinks|items|stock)|display (rack|fridge|freezer)|"
                    r"cold (storage|drinks)|more customers|extra customers|home delivery|"
                    r"whole ?sale price|bulk purchase|longer hours|second (shop|outlet)"),
    input_keys=["purchases", "raw_material", "materials"],
    margin_ok=0.20, margin_limit=0.30,
    growth_ok=0.30, growth_caution=0.60, growth_limit=1.20,
    risks={"credit sales not recovered": r"credit|debt|arrears|not pay|recover",
           "competition": r"competit|another shop|new shop|super ?market",
           "stock spoilage or expiry": r"spoil|expire|damage|slow moving|dead stock",
           "supplier price": r"supplier|price increase|wholesale price|transport cost"},
    must_cover=["market price or demand", "competition", "credit sales not recovered", "theft or damage"],
    equipment={"fridge": ["fridge", "refrigerator", "freezer", "chiller", "cooler", "cool"],
               "display": ["display", "showcase", "shelf", "shelves", "rack", "cabinet", "stand"],
               "stock": ["stock", "goods", "items", "working capital", "inventory"],
               "counter": ["counter", "cash box", "till"],
               "scale": ["scale", "weighing", "balance"],
               "shed": ["shop", "stall", "kiosk", "cabin", "boutique", "building"]},
    need_signals={"fridge": r"drinks|cold|milk|spoil|ice|yoghurt|customer ask",
                  "display": r"display|space|attract|arrange|stock|customer",
                  "stock": r"stock|variety|range|out of stock|customers? go|capital",
                  "scale": r"weigh|rice|dhal|measure|accurate"},
    compliance=[("business registration", r"business registration|br\b|registered|reg\.? no"),
                ("local authority trade licence", r"trade licen[cs]e|licen[cs]e|pradeshiya|municipal|urban council")],
    training_terms=r"technical|stock|inventory|merchandis|display|purchas|supplier|retail",
    unit_hint="item",
))

# --------------------------------------------------------------------------
# 6. tailoring and handicraft
# --------------------------------------------------------------------------
_add(Sector(
    id="tailoring", name="Tailoring, garments and handicraft",
    detect=(r"tailor|sewing|stitch|garment|dress ?mak|handicraft|craft|batik|handloom|coir|cane|reed|"
            r"weav|embroider|beeralu|lace|soft toy|bag mak|candle|soap mak|ornament|jewell"),
    specificity=[
        ("items made", r"\b(uniform|school uniform|dress|frock|shirt|saree|blouse|curtain|bag|batik|"
                        r"handloom|mat|basket|soft toy|candle|soap|jewell\w+|garment)\b", 1.5),
        ("output per week or month", r"\b(per day|per week|per month|pieces?|units?|orders?|sets?|dozens?)\b", 1.5),
        ("customers or orders", r"\b(school|shop|order|customer|exhibition|boutique|export|society)\b", 1.0),
        ("years of experience or training", EXPERIENCE, 1.0),
    ],
    market_terms=(r"school|uniform order|shop|boutique|exhibition|fair|order|customer|export|society|"
                  r"per piece|per unit|whole ?sale|online|facebook"),
    sales_basis=r"\b(per piece|per unit|pieces?|orders?|per month|per week|sets?)\b",
    growth_drivers=(r"more orders|new machine|overlock|faster|quality|finishing|design|school order|"
                    r"expand|additional (machine|worker)|training"),
    input_keys=["materials", "raw_material", "purchases"],
    margin_ok=0.45, margin_limit=0.60,
    growth_ok=0.30, growth_caution=0.60, growth_limit=1.00,
    risks={"order flow": r"order|season|demand|school term|slack",
           "material price": r"material|fabric|thread|price|supplier|import",
           "quality or rework": r"quality|reject|return|finish|damage"},
    must_cover=["market price or demand", "order flow", "equipment failure", "material price"],
    equipment={"sewing_machine": ["sewing machine", "sewing", "singer", "juki", "stitch machine"],
               "overlock": ["overlock", "over lock", "serger", "interlock", "zigzag"],
               "iron": ["iron", "steam iron", "press"],
               "cutting": ["cutting", "cutter", "scissor", "cutting table"],
               "embroidery": ["embroidery", "embroider", "computer embroidery"],
               "loom": ["loom", "handloom", "weaving", "spinning"],
               "dyeing": ["dye", "dyeing", "batik", "wax", "vat"],
               "mannequin": ["mannequin", "dummy", "display"],
               "materials": ["fabric", "cloth", "material", "thread", "yarn", "raw material"]},
    need_signals={"sewing_machine": r"order|stitch|hand|old machine|slow|capacity",
                  "overlock": r"finish|quality|edge|professional|reject",
                  "iron": r"finish|press|quality|deliver",
                  "cutting": r"cut|waste|accuracy|time",
                  "embroidery": r"design|value|order|decorat",
                  "materials": r"material|fabric|capital|order|stock"},
    compliance=[],
    training_terms=r"technical|tailor|sewing|pattern|design|cutting|finishing|craft|quality|weav",
    unit_hint="piece",
))

# --------------------------------------------------------------------------
# 7. workshop and light manufacturing
# --------------------------------------------------------------------------
_add(Sector(
    id="workshop", name="Workshop and light manufacturing",
    detect=(r"carpent|furniture|welding|weld|fabricat|aluminium|steel|block mak|cement|brick|concrete|"
            r"lathe|machin(e|ing) shop|metal|joinery|saw ?mill|masonry|tinker"),
    specificity=[
        ("products made", r"\b(chair|table|cupboard|almirah|door|window|grill|gate|block|brick|"
                           r"furniture|frame|roof|tank|rack)\b", 1.5),
        ("output per month", r"\b(per day|per week|per month|units?|pieces?|orders?|sets?|blocks?)\b", 1.5),
        ("workshop space and power", r"\b(workshop|shed|space|premises|three phase|power|electricity|yard)\b", 1.0),
        ("years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=(r"order|customer|contractor|builder|shop|hardware|house|project|per unit|per piece|"
                  r"whole ?sale|village|town|repeat order"),
    sales_basis=r"\b(per unit|per piece|units?|orders?|per month|blocks?|sets?)\b",
    growth_drivers=(r"more orders|new machine|faster|own (machine|tools)|stop hiring|quality|finishing|"
                    r"expand|additional (worker|machine)|contract"),
    input_keys=["materials", "raw_material", "purchases"],
    margin_ok=0.40, margin_limit=0.55,
    growth_ok=0.30, growth_caution=0.60, growth_limit=1.00,
    risks={"material price": r"material|timber|cement|steel|price|supplier|import",
           "order flow": r"order|season|contract|demand|rain",
           "accident or safety": r"accident|injur|safety|electric|burn|cut"},
    must_cover=["market price or demand", "material price", "equipment failure", "accident or safety"],
    equipment={"power_tool": ["drill", "grinder", "saw", "planer", "sander", "cutter", "router"],
               "welding": ["welding", "welder", "welding plant", "arc", "gas welding"],
               "lathe": ["lathe", "milling", "press machine"],
               "compressor": ["compressor", "spray gun", "air"],
               "moulds": ["mould", "mold", "block machine", "frame", "die"],
               "mixer": ["mixer", "concrete mixer", "cement mixer"],
               "materials": ["timber", "wood", "steel", "cement", "sand", "aluminium", "raw material"],
               "safety": ["helmet", "gloves", "goggles", "mask", "safety"]},
    need_signals={"power_tool": r"hand|manual|slow|hire|time|finish",
                  "welding": r"weld|hire|grill|gate|repair",
                  "compressor": r"paint|finish|spray|polish",
                  "moulds": r"block|shape|quantity|uniform",
                  "mixer": r"mix|labou?r|cement|quantity",
                  "safety": r"accident|injur|safety|risk"},
    compliance=[("local authority approval or environmental licence", r"environment(al)? (protection )?licen[cs]e|epl|local authority|pradeshiya|municipal|approval"),
                ("business registration", r"business registration|br\b|registered|reg\.? no")],
    training_terms=r"technical|carpent|weld|fabricat|machin|finishing|design|safety|quality",
    unit_hint="unit",
))

# --------------------------------------------------------------------------
# 8. personal and professional services
# --------------------------------------------------------------------------
_add(Sector(
    id="services", name="Personal and professional services",
    detect=(r"salon|beaut|barber|hair|spa|laundry|dry clean|tuition|class|nursery school|day ?care|"
            r"photograph|video|event|decor|printing|cyber|internet cafe|typing|communication cent|"
            r"massage|astrolog|catering service|cleaning|security|consult"),
    specificity=[
        ("services offered", r"\b(hair ?cut|colour|facial|bridal|dressing|massage|wash|iron|tuition|class|"
                             r"photo|video|print|typing|internet|decor|event|clean)\b", 1.5),
        ("customers per day or week", r"\b(customers? per day|clients? per|per day|per week|per month|"
                                      r"students?|bookings?|appointments?)\b", 1.5),
        ("premises or mobile service", r"\b(salon|shop|room|premises|home|mobile|visit|town|junction|rent)\b", 1.0),
        ("training or years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=(r"customers? per day|clients?|regular customer|bridal|season|wedding|school|students?|"
                  r"village|town|junction|booking|per (customer|client|student|hour|session)|facebook|whatsapp"),
    sales_basis=r"\b(per (customer|client|student|session|hour|booking)|customers? per day|students?|bookings?)\b",
    growth_drivers=(r"more customers|new service|bridal|package|equipment|quality|advertis|social media|"
                    r"expand|location|additional (chair|seat|batch)|trained"),
    input_keys=["materials", "raw_material", "purchases"],
    margin_ok=0.55, margin_limit=0.70,
    growth_ok=0.30, growth_caution=0.60, growth_limit=1.00,
    risks={"customer flow": r"customer|client|season|demand|competit|students?",
           "skill or staff": r"staff|assistant|skill|train|leave",
           "power or water": r"power ?cut|electricity|water|supply"},
    must_cover=["market price or demand", "customer flow", "equipment failure", "health or labour"],
    equipment={"salon_chair": ["salon chair", "chair", "mirror", "wash basin", "trolley"],
               "dryer": ["dryer", "hair dryer", "steamer", "straighten", "curler", "clipper", "trimmer"],
               "washing_machine": ["washing machine", "washer", "dryer machine", "iron box", "press"],
               "camera": ["camera", "lens", "tripod", "drone", "lighting", "flash"],
               "printer": ["printer", "photocopy", "scanner", "laminat", "binding"],
               "furniture": ["desk", "bench", "board", "white board", "cupboard"],
               "consumables": ["cosmetic", "shampoo", "colour", "chemical", "detergent", "paper", "ink"]},
    need_signals={"salon_chair": r"customer|wait|comfort|seat|capacity",
                  "dryer": r"time|quality|service|bridal|customer",
                  "washing_machine": r"by hand|time|volume|quality|load",
                  "camera": r"quality|photo|video|order|wedding",
                  "printer": r"print|copy|student|document|service",
                  "furniture": r"student|class|seat|space",
                  "consumables": r"material|stock|capital|service"},
    compliance=[("local authority trade licence", r"trade licen[cs]e|licen[cs]e|pradeshiya|municipal|urban council"),
                ("registration for a pre-school or tuition class", r"education (office|department)|zonal|registration|approval")],
    training_terms=r"technical|beaut|hair|salon|service|customer care|photograph|teaching|skill|hygien",
    unit_hint="customer",
))

# --------------------------------------------------------------------------
# 9. transport
# --------------------------------------------------------------------------
_add(Sector(
    id="transport", name="Transport and hiring",
    detect=(r"three ?wheel|tuk|taxi|hire|lorry|truck|van|bus|tractor hire|delivery|courier|transport|"
            r"motor ?bike (taxi|hire)|boat hire|cab|pickup"),
    specificity=[
        ("vehicle and its condition", r"(three ?wheel|tuk|van\b|lorry|truck|bus\b|motor ?(cycle|bike)|"
                                      r"tractor|pick ?up|cab\b|model|year of manufacture|registration|"
                                      r"recondition)", 1.5),
        ("trips or distance per day", r"\b(trips?|hires?|km|kilomet|per day|per week|route|runs?)\b", 1.5),
        ("rate charged", r"\b(per km|per trip|per hire|rate|fare|charge)\b", 1.0),
        ("licence and years driving", r"(driving licen[cs]e|" + EXPERIENCE + ")", 1.0),
    ],
    market_terms=(r"route|school (run|children)|office|town|junction|stand|regular (customer|hire)|contract|"
                  r"per km|per trip|fare|delivery|goods|passenger"),
    sales_basis=r"\b(per (trip|km|hire|day)|trips?|hires?|km|fare|rate)\b",
    growth_drivers=(r"own vehicle|stop renting|more trips|new route|school contract|delivery|fuel efficien|"
                    r"expand|second vehicle|app|online"),
    input_keys=["fuel", "maintenance", "spares", "raw_material"],
    margin_ok=0.40, margin_limit=0.55,
    growth_ok=0.25, growth_caution=0.50, growth_limit=0.80,
    risks={"fuel price": r"fuel|petrol|diesel|price|shortage",
           "accident or breakdown": r"accident|breakdown|repair|spare|tyre|service",
           "licence or insurance lapse": r"insurance|revenue licen[cs]e|emission|fitness|permit"},
    must_cover=["fuel price", "accident or breakdown", "market price or demand", "licence or insurance lapse"],
    equipment={"vehicle": ["three wheel", "threewheel", "tuk", "van", "lorry", "truck", "bus", "motor cycle",
                           "motorbike", "bike", "vehicle", "tractor", "cab", "pick up"],
               "spares": ["tyre", "battery", "spare", "part", "engine", "gear"],
               "meter": ["meter", "taxi meter", "gps", "tracker"],
               "canopy": ["canopy", "cover", "carrier", "rack", "seat"]},
    need_signals={"vehicle": r"rent|hire|own|daily rent|income|route|trips",
                  "spares": r"breakdown|repair|worn|safety|old",
                  "meter": r"fare|dispute|customer|app|trust",
                  "canopy": r"rain|goods|passenger|comfort|load"},
    compliance=[("revenue licence, insurance and fitness certificate", r"revenue licen[cs]e|insurance|fitness|emission"),
                ("valid driving licence", r"driving licen[cs]e|licen[cs]ed driver"),
                ("carrier or route permit where needed", r"permit|route permit|passenger|goods transport")],
    training_terms=r"defensive driving|road safety|vehicle (maintenance|care)|customer care|technical",
    unit_hint="trip",
))

# --------------------------------------------------------------------------
# 10. repair and technical services
# --------------------------------------------------------------------------
_add(Sector(
    id="repair", name="Repair and technical services",
    detect=(r"repair|servic(e|ing) cent|mechanic|garage|electrician|plumb|refrigerat|air ?condition|"
            r"electronic|mobile phone repair|computer repair|puncture|vulcaniz|watch repair|shoe repair"),
    specificity=[
        ("what is repaired", r"\b(motor ?cycle|three ?wheel|vehicle|fridge|refrigerat|air ?condition|tv|"
                             r"radio|phone|computer|pump|motor|wiring|pipe|watch|shoe|tyre)\b", 1.5),
        ("jobs per day or week", r"\b(jobs?|repairs?|units?|per day|per week|per month|customers? per day)\b", 1.5),
        ("premises and tools held", r"\b(workshop|garage|shop|premises|space|tool|junction|road)\b", 1.0),
        ("training or years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=(r"customer|village|town|junction|garage|shop|regular|per (job|repair|service)|warranty|"
                  r"call|whatsapp|contract"),
    sales_basis=r"\b(per (job|repair|service|unit)|jobs?|repairs?|per day|per month|customers? per day)\b",
    growth_drivers=(r"more jobs|new tool|faster|own (tool|equipment)|stop hiring|quality|warranty|"
                    r"additional service|trained|spare parts stock"),
    input_keys=["spares", "materials", "raw_material", "purchases"],
    margin_ok=0.55, margin_limit=0.70,
    growth_ok=0.30, growth_caution=0.60, growth_limit=1.00,
    risks={"spare parts price or supply": r"spare|part|price|supplier|import|stock",
           "skill or technology change": r"new model|technolog|skill|train|obsolete",
           "accident or safety": r"accident|injur|safety|electric|shock|burn"},
    must_cover=["market price or demand", "spare parts price or supply", "equipment failure", "accident or safety"],
    equipment={"tool_kit": ["tool kit", "tools", "spanner", "screwdriver", "socket", "wrench"],
               "tester": ["tester", "multimeter", "meter", "diagnostic", "scanner", "gauge"],
               "power_tool": ["drill", "grinder", "compressor", "soldering", "welding", "blower"],
               "spares": ["spare", "part", "gas", "refrigerant", "wire", "component"],
               "lift": ["jack", "lift", "stand", "ramp", "vice"]},
    need_signals={"tool_kit": r"hand|borrow|hire|time|job|quality",
                  "tester": r"fault|diagnos|accurate|time|guess",
                  "power_tool": r"hand|slow|quality|finish|time",
                  "spares": r"stock|customer wait|order|capital",
                  "lift": r"lift|heavy|safety|time"},
    compliance=[("local authority trade licence", r"trade licen[cs]e|licen[cs]e|pradeshiya|municipal|urban council")],
    training_terms=r"technical|repair|mechanic|electric|electronic|refrigerat|servicing|safety|diagnos",
    unit_hint="job",
))

# --------------------------------------------------------------------------
# fallback
# --------------------------------------------------------------------------
GENERIC = _add(Sector(
    id="generic", name="Other micro-enterprise",
    detect=r"business|enterprise|income generat|self employ|livelihood",
    specificity=[
        ("what is produced or sold", r"\b(product|service|item|goods|sell|produce|make|supply)\b", 1.5),
        ("output, customers or volume", r"\b(per day|per week|per month|units?|customers?|orders?|pieces?|kg)\b", 1.5),
        ("place of business", r"\b(shop|home|premises|workshop|village|town|junction|road|market)\b", 1.0),
        ("years of experience", EXPERIENCE, 1.0),
    ],
    market_terms=r"customer|buyer|shop|order|whole ?sale|market|per (unit|piece|customer)|regular|contract",
    sales_basis=r"\b(per (unit|piece|day|customer|order)|units?|orders?|customers? per day|per month)\b",
    growth_drivers=r"expand|more (orders|customers|stock|production)|new (product|service|machine)|quality|training",
    input_keys=["raw_material", "purchases", "materials"],
    margin_ok=0.45, margin_limit=0.60,
    growth_ok=0.25, growth_caution=0.50, growth_limit=1.00,
    risks={},
    must_cover=["market price or demand", "equipment failure", "health or labour", "theft or damage"],
    equipment={},
    need_signals={},
    compliance=[("business registration where required", r"business registration|br\b|registered|licen[cs]e|permit")],
    training_terms=r"technical|production|skill|service|quality",
    unit_hint="unit",
))


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------
def choose(*texts: str, override: str | None = None) -> tuple[Sector, dict[str, int]]:
    """Pick the sector whose vocabulary best fits the proposal text.

    The livelihood name and product carry more weight than the body text,
    because the body often repeats generic wording.
    """
    if override and override in SECTORS:
        return SECTORS[override], {}
    weights = [3, 3, 1, 1, 1, 1]
    scores: dict[str, int] = {}
    for sec in SECTORS.values():
        if sec.id == "generic":
            continue
        total = 0
        for i, t in enumerate(texts):
            if not t:
                continue
            w = weights[i] if i < len(weights) else 1
            total += w * len(re.findall(sec.detect, t, re.I))
        if total:
            scores[sec.id] = total
    if not scores:
        return GENERIC, scores
    best = max(scores, key=lambda k: scores[k])
    if scores[best] < 2:
        return GENERIC, scores
    return SECTORS[best], scores


def options() -> list[tuple[str, str]]:
    """(id, name) pairs for a picker, generic last."""
    rows = [(s.id, s.name) for s in SECTORS.values() if s.id != "generic"]
    return rows + [("generic", GENERIC.name)]
