"""
InnovativeDrugFinder Service

Finds innovative (non-generic, non-biosimilar) drugs approved for a given indication.

Uses a multi-source strategy:
1. MeSH standardization - get disease synonyms for comprehensive search
2. Database query - query drug_indications table
3. Web search + LLM - search the web and extract drug names with LLM
4. RxNorm deduplication - deduplicate by RxCUI
5. Curated fallback - for major indications

Filters out generics, biosimilars, OTC products, and supplements.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import anthropic
import httpx

from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
from src.drug_extraction_system.database.connection import DatabaseConnection
from src.efficacy_comparison.models import ApprovedDrug
from src.utils.config import get_settings

logger = logging.getLogger(__name__)


# Known generic manufacturers (lowercase)
GENERIC_MANUFACTURERS = {
    "teva", "sandoz", "mylan", "apotex", "dr. reddy", "dr reddy",
    "cipla", "aurobindo", "lupin", "sun pharma", "sun pharmaceutical",
    "hikma", "fresenius", "hospira", "accord", "amneal",
    "zydus", "torrent", "cadila", "wockhardt", "glenmark",
    "hetero", "alkem", "macleods", "intas", "ipca",
    "actavis", "watson", "par pharmaceutical", "barr",
    "perrigo", "major", "rugby", "qualitest",
}

# Compounding pharmacies, repackagers, and distributors to exclude
COMPOUNDING_REPACKAGERS = {
    "advanced rx", "asclemed", "bryant ranch", "prepack",
    "compounding", "pharmacy", "repack", "proficient rx",
    "a-s medication", "nucare", "rebel", "dispensing solutions",
    "kit", "cardinal health", "mckesson", "amerisource",
    "pd-rx", "readymeds", "dohmen", "stat rx", "direct rx",
    "aidarex", "golden state", "st mary's", "unit dose",
}

# Non-innovative drugs to exclude (traditional therapies, steroids, etc.)
EXCLUDED_DRUGS = {
    # Calcineurin inhibitors (topical)
    "protopic", "tacrolimus", "elidel", "pimecrolimus",
    # Traditional immunosuppressants
    "methotrexate", "azathioprine", "cyclosporine", "mycophenolate",
    "prograf", "neoral", "sandimmune", "imuran", "cellcept",
    # Steroids (unless they're a novel formulation)
    "prednisone", "prednisolone", "hydrocortisone", "triamcinolone",
    "betamethasone", "fluocinonide", "clobetasol",
    # Common OTC/antihistamines
    "benadryl", "diphenhydramine", "cetirizine", "loratadine",
    "fexofenadine", "zyrtec", "claritin", "allegra",
}

# Biosimilar suffixes (FDA naming convention: original name + 4 lowercase letters)
BIOSIMILAR_SUFFIX_PATTERN = re.compile(r'^.+-[a-z]{4}$')

# Known biosimilar brand names (not following the -xxxx suffix pattern)
# These have unique brand names but are still biosimilars
KNOWN_BIOSIMILAR_BRANDS = {
    # Adalimumab biosimilars
    "hadlima", "hyrimoz", "cyltezo", "amjevita", "idacio", "yusimry", "hulio",
    "imraldi", "hefiya", "hukyndra", "simlandi", "yuflyma",
    # Infliximab biosimilars
    "inflectra", "renflexis", "ixifi", "avsola", "zymfentra",
    # Etanercept biosimilars
    "erelzi", "eticovo",
    # Rituximab biosimilars
    "truxima", "ruxience", "riabni",
    # Tocilizumab biosimilars
    "tofidence", "tyenne",
    # Trastuzumab biosimilars
    "ogivri", "herzuma", "ontruzant", "trazimera", "kanjinti",
    # Bevacizumab biosimilars
    "mvasi", "zirabev", "alymsys", "vegzelma",
    # Pegfilgrastim biosimilars
    "fulphila", "udenyca", "ziextenzo", "nyvepria", "fylnetra",
}

# Curated list of major innovative drugs by indication (fallback)
INDICATION_DRUG_MAPPING = {
    "atopic dermatitis": [
        {"brand": "Dupixent", "generic": "dupilumab", "manufacturer": "Regeneron/Sanofi", "type": "biologic"},
        {"brand": "Adbry", "generic": "tralokinumab", "manufacturer": "LEO Pharma", "type": "biologic"},
        {"brand": "Ebglyss", "generic": "lebrikizumab", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Nemluvio", "generic": "nemolizumab", "manufacturer": "Galderma", "type": "biologic"},
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Cibinqo", "generic": "abrocitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Opzelura", "generic": "ruxolitinib", "manufacturer": "Incyte", "type": "small molecule"},
        {"brand": "Eucrisa", "generic": "crisaborole", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "eczema": [  # Alias for atopic dermatitis
        {"brand": "Dupixent", "generic": "dupilumab", "manufacturer": "Regeneron/Sanofi", "type": "biologic"},
        {"brand": "Adbry", "generic": "tralokinumab", "manufacturer": "LEO Pharma", "type": "biologic"},
        {"brand": "Ebglyss", "generic": "lebrikizumab", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Nemluvio", "generic": "nemolizumab", "manufacturer": "Galderma", "type": "biologic"},
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Cibinqo", "generic": "abrocitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Opzelura", "generic": "ruxolitinib", "manufacturer": "Incyte", "type": "small molecule"},
        {"brand": "Eucrisa", "generic": "crisaborole", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "plaque psoriasis": [
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Tremfya", "generic": "guselkumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Taltz", "generic": "ixekizumab", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Cosentyx", "generic": "secukinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Bimzelx", "generic": "bimekizumab", "manufacturer": "UCB", "type": "biologic"},
        {"brand": "Sotyktu", "generic": "deucravacitinib", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
    ],
    "rheumatoid arthritis": [
        # TNF inhibitors (major class for RA)
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Enbrel", "generic": "etanercept", "manufacturer": "Amgen/Pfizer", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Cimzia", "generic": "certolizumab pegol", "manufacturer": "UCB", "type": "biologic"},
        {"brand": "Simponi", "generic": "golimumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Simponi Aria", "generic": "golimumab", "manufacturer": "Janssen", "type": "biologic"},
        # IL-6 inhibitors
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        {"brand": "Kevzara", "generic": "sarilumab", "manufacturer": "Sanofi/Regeneron", "type": "biologic"},
        # T-cell costimulation modulator
        {"brand": "Orencia", "generic": "abatacept", "manufacturer": "Bristol-Myers Squibb", "type": "biologic"},
        # JAK inhibitors
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
        # IL-1 inhibitors
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
    ],
    "systemic lupus erythematosus": [
        {"brand": "Saphnelo", "generic": "anifrolumab", "manufacturer": "AstraZeneca", "type": "biologic"},
        {"brand": "Benlysta", "generic": "belimumab", "manufacturer": "GlaxoSmithKline", "type": "biologic"},
        {"brand": "Lupkynis", "generic": "voclosporin", "manufacturer": "Aurinia", "type": "small molecule"},
    ],
    "ulcerative colitis": [
        # JAK inhibitors
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        # S1P modulators
        {"brand": "Zeposia", "generic": "ozanimod", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
        {"brand": "Velsipity", "generic": "etrasimod", "manufacturer": "Pfizer", "type": "small molecule"},
        # IL-23 inhibitors
        {"brand": "Omvoh", "generic": "mirikizumab", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        # Integrin inhibitors
        {"brand": "Entyvio", "generic": "vedolizumab", "manufacturer": "Takeda", "type": "biologic"},
        # IL-12/23 inhibitor
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        # TNF inhibitors
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Simponi", "generic": "golimumab", "manufacturer": "Janssen", "type": "biologic"},
    ],
    "crohn's disease": [
        # JAK inhibitors
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        # IL-23 inhibitors
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        # Integrin inhibitors
        {"brand": "Entyvio", "generic": "vedolizumab", "manufacturer": "Takeda", "type": "biologic"},
        # IL-12/23 inhibitor
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        # TNF inhibitors
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Cimzia", "generic": "certolizumab pegol", "manufacturer": "UCB", "type": "biologic"},
    ],
    "crohn disease": [  # Alias without apostrophe
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Entyvio", "generic": "vedolizumab", "manufacturer": "Takeda", "type": "biologic"},
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Cimzia", "generic": "certolizumab pegol", "manufacturer": "UCB", "type": "biologic"},
    ],
    "inflammatory bowel disease": [  # General term covering UC and Crohn's
        # Drugs approved for both UC and Crohn's
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Entyvio", "generic": "vedolizumab", "manufacturer": "Takeda", "type": "biologic"},
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Cimzia", "generic": "certolizumab pegol", "manufacturer": "UCB", "type": "biologic"},
        {"brand": "Zeposia", "generic": "ozanimod", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "ibd": [  # Alias for inflammatory bowel disease
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Entyvio", "generic": "vedolizumab", "manufacturer": "Takeda", "type": "biologic"},
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
    ],
    # Rare/orphan autoimmune diseases
    "adult-onset still's disease": [
        # IL-1 inhibitors (FDA approved for AOSD)
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
        # IL-6 inhibitors (used off-label, not FDA approved for AOSD specifically)
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        {"brand": "Kevzara", "generic": "sarilumab", "manufacturer": "Sanofi/Regeneron", "type": "biologic"},
    ],
    "still's disease": [  # Alias
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
    ],
    "takayasu arteritis": [
        # IL-6 inhibitors (Actemra FDA approved for GCA, used for Takayasu)
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        # TNF inhibitors (used off-label)
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
    ],
    "sjogren's syndrome": [
        # Note: No FDA-approved biologics specifically for Sjögren's
        # These are symptom-management drugs, not disease-modifying
        {"brand": "Evoxac", "generic": "cevimeline", "manufacturer": "Daiichi Sankyo", "type": "small molecule"},
        {"brand": "Salagen", "generic": "pilocarpine", "manufacturer": "Eisai", "type": "small molecule"},
        # Rituximab used off-label but not FDA approved for Sjögren's
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "sjogren's disease": [  # Alias
        {"brand": "Evoxac", "generic": "cevimeline", "manufacturer": "Daiichi Sankyo", "type": "small molecule"},
        {"brand": "Salagen", "generic": "pilocarpine", "manufacturer": "Eisai", "type": "small molecule"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "granuloma annulare": [
        # Note: No FDA-approved treatments specifically for granuloma annulare
        # All treatments are off-label; listing commonly studied biologics
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Dupixent", "generic": "dupilumab", "manufacturer": "Regeneron/Sanofi", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "lichen planopilaris": [
        # Note: No FDA-approved treatments specifically for lichen planopilaris
        # Listing drugs commonly studied in case series/trials
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
        {"brand": "Dupixent", "generic": "dupilumab", "manufacturer": "Regeneron/Sanofi", "type": "biologic"},
    ],
    "pemphigus vulgaris": [
        # Rituximab FDA approved for pemphigus vulgaris (2018)
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "pemphigus": [  # Broader alias
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    # Giant cell arteritis (related to Takayasu)
    "giant cell arteritis": [
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        {"brand": "Kevzara", "generic": "sarilumab", "manufacturer": "Sanofi/Regeneron", "type": "biologic"},
    ],
    # =========================================================================
    # DISEASES FROM CASE SERIES ANALYSIS (top conditions by paper count)
    # =========================================================================
    "dermatomyositis": [
        # JAK inhibitors (most studied)
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        # Biologics
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        # IVIG (not strictly innovative but widely used)
    ],
    "myasthenia gravis": [
        # FcRn inhibitors (FDA approved)
        {"brand": "Vyvgart", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
        {"brand": "Rystiggo", "generic": "rozanolixizumab", "manufacturer": "UCB", "type": "biologic"},
        # Complement inhibitors
        {"brand": "Soliris", "generic": "eculizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Ultomiris", "generic": "ravulizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Zilbrysq", "generic": "zilucoplan", "manufacturer": "UCB", "type": "small molecule"},
        # B-cell depletion
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "multiple sclerosis": [
        # B-cell therapies
        {"brand": "Ocrevus", "generic": "ocrelizumab", "manufacturer": "Genentech", "type": "biologic"},
        {"brand": "Kesimpta", "generic": "ofatumumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        # S1P modulators
        {"brand": "Gilenya", "generic": "fingolimod", "manufacturer": "Novartis", "type": "small molecule"},
        {"brand": "Mayzent", "generic": "siponimod", "manufacturer": "Novartis", "type": "small molecule"},
        {"brand": "Zeposia", "generic": "ozanimod", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
        {"brand": "Ponvory", "generic": "ponesimod", "manufacturer": "Janssen", "type": "small molecule"},
        # BTK inhibitors
        {"brand": "Tecfidera", "generic": "dimethyl fumarate", "manufacturer": "Biogen", "type": "small molecule"},
        {"brand": "Tysabri", "generic": "natalizumab", "manufacturer": "Biogen", "type": "biologic"},
        {"brand": "Lemtrada", "generic": "alemtuzumab", "manufacturer": "Sanofi", "type": "biologic"},
    ],
    "alopecia areata": [
        # JAK inhibitors (FDA approved)
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
        {"brand": "Litfulo", "generic": "ritlecitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        # Off-label JAK inhibitors
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Cibinqo", "generic": "abrocitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
    ],
    "familial mediterranean fever": [
        # IL-1 inhibitors (FDA approved)
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        # Colchicine (traditional, not innovative)
    ],
    "hemophagocytic lymphohistiocytosis": [
        # IFN-gamma inhibitor (FDA approved for primary HLH)
        {"brand": "Gamifant", "generic": "emapalumab", "manufacturer": "Sobi", "type": "biologic"},
        # IL-1 inhibitors
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        # JAK inhibitors (emerging)
        {"brand": "Jakafi", "generic": "ruxolitinib", "manufacturer": "Incyte", "type": "small molecule"},
    ],
    "macrophage activation syndrome": [
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        {"brand": "Jakafi", "generic": "ruxolitinib", "manufacturer": "Incyte", "type": "small molecule"},
    ],
    "systemic sclerosis": [
        # Biologics
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        {"brand": "Actemra", "generic": "tocilizumab", "manufacturer": "Genentech", "type": "biologic"},
        # Antifibrotics
        {"brand": "Ofev", "generic": "nintedanib", "manufacturer": "Boehringer Ingelheim", "type": "small molecule"},
        # JAK inhibitors (emerging)
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "lichen planus": [
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
        {"brand": "Cibinqo", "generic": "abrocitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Sotyktu", "generic": "deucravacitinib", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
    ],
    "vitiligo": [
        # JAK inhibitors (FDA approved)
        {"brand": "Opzelura", "generic": "ruxolitinib", "manufacturer": "Incyte", "type": "small molecule"},
        # Off-label
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "immune thrombocytopenia": [
        # TPO-RAs (FDA approved)
        {"brand": "Promacta", "generic": "eltrombopag", "manufacturer": "Novartis", "type": "small molecule"},
        {"brand": "Nplate", "generic": "romiplostim", "manufacturer": "Amgen", "type": "biologic"},
        {"brand": "Doptelet", "generic": "avatrombopag", "manufacturer": "Sobi", "type": "small molecule"},
        # Spleen tyrosine kinase inhibitor
        {"brand": "Tavalisse", "generic": "fostamatinib", "manufacturer": "Rigel", "type": "small molecule"},
        # FcRn inhibitor
        {"brand": "Vyvgart", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
        # B-cell depletion
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "pericarditis": [
        # IL-1 inhibitors
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Arcalyst", "generic": "rilonacept", "manufacturer": "Kiniksa", "type": "biologic"},
    ],
    "recurrent pericarditis": [
        {"brand": "Arcalyst", "generic": "rilonacept", "manufacturer": "Kiniksa", "type": "biologic"},
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
    ],
    "bullous pemphigoid": [
        # FDA approved
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        # Emerging treatments
        {"brand": "Dupixent", "generic": "dupilumab", "manufacturer": "Regeneron/Sanofi", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "neuromyelitis optica": [
        # FDA approved
        {"brand": "Soliris", "generic": "eculizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Uplizna", "generic": "inebilizumab", "manufacturer": "Horizon", "type": "biologic"},
        {"brand": "Enspryng", "generic": "satralizumab", "manufacturer": "Genentech", "type": "biologic"},
        # Off-label
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "neuromyelitis optica spectrum disorder": [
        {"brand": "Soliris", "generic": "eculizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Uplizna", "generic": "inebilizumab", "manufacturer": "Horizon", "type": "biologic"},
        {"brand": "Enspryng", "generic": "satralizumab", "manufacturer": "Genentech", "type": "biologic"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "pyoderma gangrenosum": [
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "gout": [
        # Urate-lowering (IL-1 for acute flares)
        {"brand": "Krystexxa", "generic": "pegloticase", "manufacturer": "Horizon", "type": "biologic"},
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Arcalyst", "generic": "rilonacept", "manufacturer": "Kiniksa", "type": "biologic"},
    ],
    "kawasaki disease": [
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
    ],
    "cutaneous lupus erythematosus": [
        {"brand": "Saphnelo", "generic": "anifrolumab", "manufacturer": "AstraZeneca", "type": "biologic"},
        {"brand": "Benlysta", "generic": "belimumab", "manufacturer": "GlaxoSmithKline", "type": "biologic"},
        {"brand": "Sotyktu", "generic": "deucravacitinib", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
    ],
    "uveitis": [
        # FDA approved
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        # Off-label
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "inflammatory myopathies": [
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "scleritis": [
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "autoimmune encephalitis": [
        {"brand": "Vyvgart", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "prurigo nodularis": [
        {"brand": "Dupixent", "generic": "dupilumab", "manufacturer": "Regeneron/Sanofi", "type": "biologic"},
        {"brand": "Nemluvio", "generic": "nemolizumab", "manufacturer": "Galderma", "type": "biologic"},
        {"brand": "Cibinqo", "generic": "abrocitinib", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "sarcoidosis": [
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "sapho syndrome": [
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "autoimmune hepatitis": [
        {"brand": "Benlysta", "generic": "belimumab", "manufacturer": "GlaxoSmithKline", "type": "biologic"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "schnitzler syndrome": [
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
    ],
    "blau syndrome": [
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "aicardi-goutieres syndrome": [
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
    ],
    "sting-associated vasculopathy": [
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Olumiant", "generic": "baricitinib", "manufacturer": "Eli Lilly", "type": "small molecule"},
    ],
    "hidradenitis suppurativa": [
        # FDA approved
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Cosentyx", "generic": "secukinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Bimzelx", "generic": "bimekizumab", "manufacturer": "UCB", "type": "biologic"},
    ],
    "behcet's disease": [
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
        {"brand": "Ilaris", "generic": "canakinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Cosentyx", "generic": "secukinumab", "manufacturer": "Novartis", "type": "biologic"},
    ],
    "behcet disease": [  # Alias
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Kineret", "generic": "anakinra", "manufacturer": "Sobi", "type": "biologic"},
    ],
    "lupus nephritis": [
        {"brand": "Benlysta", "generic": "belimumab", "manufacturer": "GlaxoSmithKline", "type": "biologic"},
        {"brand": "Lupkynis", "generic": "voclosporin", "manufacturer": "Aurinia", "type": "small molecule"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "anca-associated vasculitis": [
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        {"brand": "Tavneos", "generic": "avacopan", "manufacturer": "ChemoCentryx", "type": "small molecule"},
    ],
    "granulomatosis with polyangiitis": [
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
        {"brand": "Tavneos", "generic": "avacopan", "manufacturer": "ChemoCentryx", "type": "small molecule"},
    ],
    "chronic inflammatory demyelinating polyneuropathy": [
        {"brand": "Vyvgart Hytrulo", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
    ],
    "paroxysmal nocturnal hemoglobinuria": [
        {"brand": "Soliris", "generic": "eculizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Ultomiris", "generic": "ravulizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Empaveli", "generic": "pegcetacoplan", "manufacturer": "Apellis", "type": "biologic"},
        {"brand": "Fabhalta", "generic": "iptacopan", "manufacturer": "Novartis", "type": "small molecule"},
    ],
    "atypical hemolytic uremic syndrome": [
        {"brand": "Soliris", "generic": "eculizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Ultomiris", "generic": "ravulizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Fabhalta", "generic": "iptacopan", "manufacturer": "Novartis", "type": "small molecule"},
    ],
    "cold agglutinin disease": [
        {"brand": "Enjaymo", "generic": "sutimlimab", "manufacturer": "Sanofi", "type": "biologic"},
    ],
    "c3 glomerulopathy": [
        {"brand": "Fabhalta", "generic": "iptacopan", "manufacturer": "Novartis", "type": "small molecule"},
    ],
    "iga nephropathy": [
        {"brand": "Filspari", "generic": "sparsentan", "manufacturer": "Travere", "type": "small molecule"},
        {"brand": "Tarpeyo", "generic": "budesonide", "manufacturer": "Calliditas", "type": "small molecule"},
    ],
    "igan": [  # Alias for IgA nephropathy
        {"brand": "Filspari", "generic": "sparsentan", "manufacturer": "Travere", "type": "small molecule"},
        {"brand": "Tarpeyo", "generic": "budesonide", "manufacturer": "Calliditas", "type": "small molecule"},
    ],
    # =========================================================================
    # TYPE 1 DIABETES
    # =========================================================================
    "type 1 diabetes": [
        # CD3-directed antibody (delays onset of clinical T1D)
        {"brand": "Tzield", "generic": "teplizumab", "manufacturer": "Provention Bio/Sanofi", "type": "biologic"},
    ],
    "t1d": [  # Alias
        {"brand": "Tzield", "generic": "teplizumab", "manufacturer": "Provention Bio/Sanofi", "type": "biologic"},
    ],
    "type 1 diabetes mellitus": [  # Alias
        {"brand": "Tzield", "generic": "teplizumab", "manufacturer": "Provention Bio/Sanofi", "type": "biologic"},
    ],
    # =========================================================================
    # KIDNEY DISEASES
    # =========================================================================
    "apol1-mediated kidney disease": [
        # Note: No FDA-approved drugs specifically for AMKD yet
        # VX-147 (inaxaplin) in Phase 3 trials
        # SGLT2 inhibitors used off-label for kidney protection
        {"brand": "Farxiga", "generic": "dapagliflozin", "manufacturer": "AstraZeneca", "type": "small molecule"},
        {"brand": "Jardiance", "generic": "empagliflozin", "manufacturer": "Boehringer Ingelheim/Eli Lilly", "type": "small molecule"},
    ],
    "amkd": [  # Alias for APOL1-mediated kidney disease
        {"brand": "Farxiga", "generic": "dapagliflozin", "manufacturer": "AstraZeneca", "type": "small molecule"},
        {"brand": "Jardiance", "generic": "empagliflozin", "manufacturer": "Boehringer Ingelheim/Eli Lilly", "type": "small molecule"},
    ],
    "autosomal dominant polycystic kidney disease": [
        {"brand": "Jynarque", "generic": "tolvaptan", "manufacturer": "Otsuka", "type": "small molecule"},
    ],
    "adpkd": [  # Alias
        {"brand": "Jynarque", "generic": "tolvaptan", "manufacturer": "Otsuka", "type": "small molecule"},
    ],
    "polycystic kidney disease": [  # Broader alias
        {"brand": "Jynarque", "generic": "tolvaptan", "manufacturer": "Otsuka", "type": "small molecule"},
    ],
    "primary membranous nephropathy": [
        # Rituximab is standard of care (off-label but widely used)
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "pmn": [  # Alias
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "membranous nephropathy": [  # Broader alias
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    # =========================================================================
    # HEMATOLOGIC DISORDERS
    # =========================================================================
    "beta thalassemia": [
        # Gene therapies
        {"brand": "Casgevy", "generic": "exagamglogene autotemcel", "manufacturer": "Vertex/CRISPR Therapeutics", "type": "gene therapy"},
        {"brand": "Lyfgenia", "generic": "lovotibeglogene autotemcel", "manufacturer": "bluebird bio", "type": "gene therapy"},
        {"brand": "Zynteglo", "generic": "betibeglogene autotemcel", "manufacturer": "bluebird bio", "type": "gene therapy"},
        # Erythroid maturation agent
        {"brand": "Reblozyl", "generic": "luspatercept", "manufacturer": "Bristol-Myers Squibb", "type": "biologic"},
    ],
    "beta-thalassemia": [  # Alias with hyphen
        {"brand": "Casgevy", "generic": "exagamglogene autotemcel", "manufacturer": "Vertex/CRISPR Therapeutics", "type": "gene therapy"},
        {"brand": "Lyfgenia", "generic": "lovotibeglogene autotemcel", "manufacturer": "bluebird bio", "type": "gene therapy"},
        {"brand": "Zynteglo", "generic": "betibeglogene autotemcel", "manufacturer": "bluebird bio", "type": "gene therapy"},
        {"brand": "Reblozyl", "generic": "luspatercept", "manufacturer": "Bristol-Myers Squibb", "type": "biologic"},
    ],
    "transfusion-dependent beta thalassemia": [  # Specific indication
        {"brand": "Casgevy", "generic": "exagamglogene autotemcel", "manufacturer": "Vertex/CRISPR Therapeutics", "type": "gene therapy"},
        {"brand": "Lyfgenia", "generic": "lovotibeglogene autotemcel", "manufacturer": "bluebird bio", "type": "gene therapy"},
        {"brand": "Zynteglo", "generic": "betibeglogene autotemcel", "manufacturer": "bluebird bio", "type": "gene therapy"},
        {"brand": "Reblozyl", "generic": "luspatercept", "manufacturer": "Bristol-Myers Squibb", "type": "biologic"},
    ],
    # =========================================================================
    # MUSCULAR DYSTROPHIES
    # =========================================================================
    "duchenne muscular dystrophy": [
        # Gene therapy
        {"brand": "Elevidys", "generic": "delandistrogene moxeparvovec", "manufacturer": "Sarepta", "type": "gene therapy"},
        # Exon-skipping therapies
        {"brand": "Exondys 51", "generic": "eteplirsen", "manufacturer": "Sarepta", "type": "antisense oligonucleotide"},
        {"brand": "Vyondys 53", "generic": "golodirsen", "manufacturer": "Sarepta", "type": "antisense oligonucleotide"},
        {"brand": "Viltepso", "generic": "viltolarsen", "manufacturer": "NS Pharma", "type": "antisense oligonucleotide"},
        {"brand": "Amondys 45", "generic": "casimersen", "manufacturer": "Sarepta", "type": "antisense oligonucleotide"},
        # Corticosteroid (novel formulation)
        {"brand": "Emflaza", "generic": "deflazacort", "manufacturer": "PTC Therapeutics", "type": "small molecule"},
    ],
    "dmd": [  # Alias
        {"brand": "Elevidys", "generic": "delandistrogene moxeparvovec", "manufacturer": "Sarepta", "type": "gene therapy"},
        {"brand": "Exondys 51", "generic": "eteplirsen", "manufacturer": "Sarepta", "type": "antisense oligonucleotide"},
        {"brand": "Vyondys 53", "generic": "golodirsen", "manufacturer": "Sarepta", "type": "antisense oligonucleotide"},
        {"brand": "Viltepso", "generic": "viltolarsen", "manufacturer": "NS Pharma", "type": "antisense oligonucleotide"},
        {"brand": "Amondys 45", "generic": "casimersen", "manufacturer": "Sarepta", "type": "antisense oligonucleotide"},
        {"brand": "Emflaza", "generic": "deflazacort", "manufacturer": "PTC Therapeutics", "type": "small molecule"},
    ],
    "myotonic dystrophy type 1": [
        # Note: No FDA-approved disease-modifying therapies for DM1 yet
        # Mexiletine approved in EU for myotonia symptoms
        # Listing drugs commonly studied in trials
        {"brand": "Namuscla", "generic": "mexiletine", "manufacturer": "Lupin", "type": "small molecule"},
    ],
    "dm1": [  # Alias
        {"brand": "Namuscla", "generic": "mexiletine", "manufacturer": "Lupin", "type": "small molecule"},
    ],
    "myotonic dystrophy": [  # Broader alias
        {"brand": "Namuscla", "generic": "mexiletine", "manufacturer": "Lupin", "type": "small molecule"},
    ],
    "thyroid eye disease": [
        {"brand": "Tepezza", "generic": "teprotumumab", "manufacturer": "Horizon", "type": "biologic"},
    ],
    "graves orbitopathy": [
        {"brand": "Tepezza", "generic": "teprotumumab", "manufacturer": "Horizon", "type": "biologic"},
    ],
    # =========================================================================
    # PSORIASIS AND PSORIATIC ARTHRITIS
    # =========================================================================
    "psoriasis": [  # General alias for plaque psoriasis
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Tremfya", "generic": "guselkumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Taltz", "generic": "ixekizumab", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Cosentyx", "generic": "secukinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Bimzelx", "generic": "bimekizumab", "manufacturer": "UCB", "type": "biologic"},
        {"brand": "Sotyktu", "generic": "deucravacitinib", "manufacturer": "Bristol-Myers Squibb", "type": "small molecule"},
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Enbrel", "generic": "etanercept", "manufacturer": "Amgen/Pfizer", "type": "biologic"},
        {"brand": "Cimzia", "generic": "certolizumab pegol", "manufacturer": "UCB", "type": "biologic"},
    ],
    "psoriatic arthritis": [
        # IL-17 inhibitors
        {"brand": "Cosentyx", "generic": "secukinumab", "manufacturer": "Novartis", "type": "biologic"},
        {"brand": "Taltz", "generic": "ixekizumab", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Bimzelx", "generic": "bimekizumab", "manufacturer": "UCB", "type": "biologic"},
        # IL-23 inhibitors
        {"brand": "Tremfya", "generic": "guselkumab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Skyrizi", "generic": "risankizumab", "manufacturer": "AbbVie", "type": "biologic"},
        # IL-12/23 inhibitor
        {"brand": "Stelara", "generic": "ustekinumab", "manufacturer": "Janssen", "type": "biologic"},
        # TNF inhibitors
        {"brand": "Humira", "generic": "adalimumab", "manufacturer": "AbbVie", "type": "biologic"},
        {"brand": "Enbrel", "generic": "etanercept", "manufacturer": "Amgen/Pfizer", "type": "biologic"},
        {"brand": "Remicade", "generic": "infliximab", "manufacturer": "Janssen", "type": "biologic"},
        {"brand": "Cimzia", "generic": "certolizumab pegol", "manufacturer": "UCB", "type": "biologic"},
        {"brand": "Simponi", "generic": "golimumab", "manufacturer": "Janssen", "type": "biologic"},
        # JAK inhibitors
        {"brand": "Xeljanz", "generic": "tofacitinib", "manufacturer": "Pfizer", "type": "small molecule"},
        {"brand": "Rinvoq", "generic": "upadacitinib", "manufacturer": "AbbVie", "type": "small molecule"},
        # T-cell modulator
        {"brand": "Orencia", "generic": "abatacept", "manufacturer": "Bristol-Myers Squibb", "type": "biologic"},
        # PDE4 inhibitor
        {"brand": "Otezla", "generic": "apremilast", "manufacturer": "Amgen", "type": "small molecule"},
    ],
    # =========================================================================
    # FcRn INHIBITOR INDICATIONS (aliases for existing entries)
    # =========================================================================
    "generalized myasthenia gravis": [  # Alias - FcRn inhibitors approved
        {"brand": "Vyvgart", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
        {"brand": "Vyvgart Hytrulo", "generic": "efgartigimod/hyaluronidase", "manufacturer": "argenx", "type": "biologic"},
        {"brand": "Rystiggo", "generic": "rozanolixizumab", "manufacturer": "UCB", "type": "biologic"},
        {"brand": "Soliris", "generic": "eculizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Ultomiris", "generic": "ravulizumab", "manufacturer": "Alexion", "type": "biologic"},
        {"brand": "Zilbrysq", "generic": "zilucoplan", "manufacturer": "UCB", "type": "small molecule"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "cidp": [  # Alias for chronic inflammatory demyelinating polyneuropathy
        {"brand": "Vyvgart Hytrulo", "generic": "efgartigimod/hyaluronidase", "manufacturer": "argenx", "type": "biologic"},
    ],
    "immune thrombocytopenic purpura": [  # FcRn inhibitors also approved here
        {"brand": "Vyvgart", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
        {"brand": "Promacta", "generic": "eltrombopag", "manufacturer": "Novartis", "type": "small molecule"},
        {"brand": "Nplate", "generic": "romiplostim", "manufacturer": "Amgen", "type": "biologic"},
        {"brand": "Doptelet", "generic": "avatrombopag", "manufacturer": "Sobi", "type": "small molecule"},
        {"brand": "Tavalisse", "generic": "fostamatinib", "manufacturer": "Rigel", "type": "small molecule"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    "itp": [  # Alias for immune thrombocytopenic purpura
        {"brand": "Vyvgart", "generic": "efgartigimod", "manufacturer": "argenx", "type": "biologic"},
        {"brand": "Promacta", "generic": "eltrombopag", "manufacturer": "Novartis", "type": "small molecule"},
        {"brand": "Nplate", "generic": "romiplostim", "manufacturer": "Amgen", "type": "biologic"},
        {"brand": "Doptelet", "generic": "avatrombopag", "manufacturer": "Sobi", "type": "small molecule"},
        {"brand": "Tavalisse", "generic": "fostamatinib", "manufacturer": "Rigel", "type": "small molecule"},
        {"brand": "Rituxan", "generic": "rituximab", "manufacturer": "Genentech/Biogen", "type": "biologic"},
    ],
    # =========================================================================
    # OBESITY / WEIGHT MANAGEMENT
    # =========================================================================
    "obesity": [
        # GLP-1 receptor agonists
        {"brand": "Wegovy", "generic": "semaglutide", "manufacturer": "Novo Nordisk", "type": "biologic"},
        {"brand": "Zepbound", "generic": "tirzepatide", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Saxenda", "generic": "liraglutide", "manufacturer": "Novo Nordisk", "type": "biologic"},
        # Combination therapies
        {"brand": "Contrave", "generic": "naltrexone/bupropion", "manufacturer": "Currax", "type": "small molecule"},
        {"brand": "Qsymia", "generic": "phentermine/topiramate", "manufacturer": "Vivus", "type": "small molecule"},
    ],
    "chronic weight management": [  # Alias for obesity
        {"brand": "Wegovy", "generic": "semaglutide", "manufacturer": "Novo Nordisk", "type": "biologic"},
        {"brand": "Zepbound", "generic": "tirzepatide", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Saxenda", "generic": "liraglutide", "manufacturer": "Novo Nordisk", "type": "biologic"},
        {"brand": "Contrave", "generic": "naltrexone/bupropion", "manufacturer": "Currax", "type": "small molecule"},
        {"brand": "Qsymia", "generic": "phentermine/topiramate", "manufacturer": "Vivus", "type": "small molecule"},
    ],
    "weight management": [  # Another alias
        {"brand": "Wegovy", "generic": "semaglutide", "manufacturer": "Novo Nordisk", "type": "biologic"},
        {"brand": "Zepbound", "generic": "tirzepatide", "manufacturer": "Eli Lilly", "type": "biologic"},
        {"brand": "Saxenda", "generic": "liraglutide", "manufacturer": "Novo Nordisk", "type": "biologic"},
        {"brand": "Contrave", "generic": "naltrexone/bupropion", "manufacturer": "Currax", "type": "small molecule"},
        {"brand": "Qsymia", "generic": "phentermine/topiramate", "manufacturer": "Vivus", "type": "small molecule"},
    ],
}


@dataclass
class DrugCandidate:
    """Candidate drug from OpenFDA search before validation."""
    brand_name: str
    generic_name: Optional[str]
    manufacturer: Optional[str]
    application_number: Optional[str]
    indications_text: str
    drug_type: Optional[str] = None


class IndicationValidator:
    """
    LLM-based validator to confirm if a drug is approved for an indication.

    Uses Haiku for fast validation, escalates to Sonnet if confidence is low.
    """

    VALIDATION_PROMPT = """You are a pharmaceutical regulatory expert. Analyze this FDA drug label excerpt and determine if the drug is FDA-approved for the specified indication.

Drug: {drug_name}
Indication to check: {indication}

FDA Label - Indications and Usage section:
{indications_text}

IMPORTANT: The drug must be APPROVED (indicated) for this condition, not just mentioned in clinical trials or as a contraindication.

Respond with ONLY a JSON object (no other text):
{{
    "is_approved": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}"""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.haiku_model = "claude-3-5-haiku-20241022"
        self.sonnet_model = "claude-sonnet-4-20250514"

    def validate(
        self,
        drug_name: str,
        indication: str,
        indications_text: str,
        confidence_threshold: float = 0.8,
    ) -> Tuple[bool, float, str]:
        """
        Validate if a drug is approved for an indication.

        Args:
            drug_name: Drug brand name
            indication: Disease/condition to check
            indications_text: FDA label indications_and_usage text
            confidence_threshold: If Haiku confidence < this, escalate to Sonnet

        Returns:
            Tuple of (is_approved, confidence, reason)
        """
        # Truncate very long indication text
        if len(indications_text) > 4000:
            indications_text = indications_text[:4000] + "..."

        prompt = self.VALIDATION_PROMPT.format(
            drug_name=drug_name,
            indication=indication,
            indications_text=indications_text,
        )

        # Try Haiku first
        is_approved, confidence, reason = self._call_llm(prompt, self.haiku_model)

        # Escalate to Sonnet if low confidence
        if confidence < confidence_threshold:
            logger.info(f"Haiku confidence {confidence:.0%} < {confidence_threshold:.0%}, escalating to Sonnet for {drug_name}")
            is_approved, confidence, reason = self._call_llm(prompt, self.sonnet_model)

        return is_approved, confidence, reason

    def validate_batch(
        self,
        candidates: List[DrugCandidate],
        indication: str,
    ) -> List[Tuple[DrugCandidate, bool, float]]:
        """
        Validate multiple drug candidates in a batch.

        For efficiency, sends multiple candidates in one prompt to Haiku.

        Args:
            candidates: List of drug candidates to validate
            indication: Disease/condition to check

        Returns:
            List of (candidate, is_approved, confidence) tuples
        """
        if not candidates:
            return []

        # For small batches, validate individually
        if len(candidates) <= 3:
            results = []
            for candidate in candidates:
                is_approved, confidence, _ = self.validate(
                    candidate.brand_name,
                    indication,
                    candidate.indications_text,
                )
                results.append((candidate, is_approved, confidence))
            return results

        # For larger batches, use batch prompt
        return self._validate_batch_prompt(candidates, indication)

    def _validate_batch_prompt(
        self,
        candidates: List[DrugCandidate],
        indication: str,
    ) -> List[Tuple[DrugCandidate, bool, float]]:
        """Validate multiple candidates in a single LLM call."""

        drugs_section = ""
        for i, c in enumerate(candidates, 1):
            text = c.indications_text[:2000] if len(c.indications_text) > 2000 else c.indications_text
            drugs_section += f"""
Drug {i}: {c.brand_name}
Indications text: {text}
---
"""

        prompt = f"""You are a pharmaceutical regulatory expert. For each drug below, determine if it is FDA-approved for: {indication}

{drugs_section}

Respond with ONLY a JSON array (no other text):
[
    {{"drug": "DrugName1", "is_approved": true/false, "confidence": 0.0-1.0}},
    ...
]"""

        try:
            response = self.client.messages.create(
                model=self.haiku_model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()

            # Parse JSON
            if "```" in result_text:
                result_text = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_text)
                result_text = result_text.group(1) if result_text else "[]"

            results_data = json.loads(result_text)

            # Map results back to candidates
            results = []
            for i, candidate in enumerate(candidates):
                if i < len(results_data):
                    r = results_data[i]
                    results.append((candidate, r.get("is_approved", False), r.get("confidence", 0.5)))
                else:
                    results.append((candidate, False, 0.0))

            return results

        except Exception as e:
            logger.error(f"Batch validation failed: {e}")
            # Fall back to individual validation
            results = []
            for candidate in candidates:
                is_approved, confidence, _ = self.validate(
                    candidate.brand_name,
                    indication,
                    candidate.indications_text,
                )
                results.append((candidate, is_approved, confidence))
            return results

    def _call_llm(self, prompt: str, model: str) -> Tuple[bool, float, str]:
        """Call LLM and parse response."""
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()

            # Parse JSON response
            if "```" in result_text:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_text)
                result_text = match.group(1) if match else result_text

            # Find JSON object
            start = result_text.find("{")
            end = result_text.rfind("}") + 1
            if start >= 0 and end > start:
                result_text = result_text[start:end]

            result = json.loads(result_text)

            return (
                result.get("is_approved", False),
                result.get("confidence", 0.5),
                result.get("reason", ""),
            )

        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            return False, 0.0, str(e)


class WebSearchDrugDiscovery:
    """
    Discovers drugs using web search + LLM extraction.

    This approach is more reliable than OpenFDA text search for finding
    innovative drugs because:
    - Web sources have curated lists of FDA-approved drugs by indication
    - LLM can understand context and extract structured data
    - Works for newer drugs that may not be well-indexed in APIs
    """

    EXTRACTION_PROMPT = """You are a pharmaceutical expert extracting FDA-approved drugs for a specific indication from web search results.

Indication: {indication}

Search Results:
{search_results}

Extract ALL brand name prescription drugs that are FDA-approved for {indication}.

INCLUDE:
- Innovative branded drugs (NDA or BLA approved)
- Biologics, small molecules, targeted therapies, gene therapies, cell therapies
- First-in-class drugs and newer entrants

EXCLUDE:
- Generic drugs (ANDA approved)
- Biosimilars (names ending in -xxxx suffix like adalimumab-xxxx)
- OTC products
- Supplements and vitamins
- Traditional immunosuppressants (tacrolimus/Protopic, cyclosporine, methotrexate, azathioprine, mycophenolate)
- Calcineurin inhibitors (Protopic, Elidel) unless they are truly novel
- Corticosteroids (prednisone, hydrocortisone, etc.)
- Antihistamines
- Compounded preparations

For each drug, provide:
- brand_name: The commercial brand name (e.g., "Keytruda", "Humira", "Ozempic")
- generic_name: The active ingredient name (e.g., "pembrolizumab", "adalimumab", "semaglutide")
- manufacturer: The pharmaceutical company (e.g., "Merck", "AbbVie", "Novo Nordisk")
- drug_class: The mechanism/therapeutic class (e.g., "PD-1 inhibitor", "TNF inhibitor", "GLP-1 agonist")

Respond with ONLY a JSON array (no other text):
[
    {{"brand_name": "DrugBrand", "generic_name": "druggeneric", "manufacturer": "Pharma Co", "drug_class": "Drug Class"}},
    ...
]

If no drugs are found, return an empty array: []"""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-3-5-haiku-20241022"

    async def search_drugs_for_indication(self, indication: str) -> List[DrugCandidate]:
        """
        Search the web for FDA-approved drugs for an indication.

        Args:
            indication: Disease/condition name

        Returns:
            List of DrugCandidate objects
        """
        # Build search queries - generic enough for any therapeutic area
        queries = [
            f"FDA approved prescription drugs for {indication} brand name list site:fda.gov OR site:drugs.com OR site:medscape.com",
            f"FDA approved treatments {indication} 2024 2025 new drugs biologics",
        ]

        all_search_results = []

        # Perform web searches using DuckDuckGo
        for query in queries:
            try:
                results = await self._duckduckgo_search(query)
                if results:
                    all_search_results.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for query '{query}': {e}")

        if not all_search_results:
            logger.warning(f"No web search results for {indication}, falling back to LLM knowledge")
            return self.extract_drugs_from_knowledge(indication)

        # Combine search results into text
        search_text = self._format_search_results(all_search_results)

        # Extract drugs using LLM
        drugs = self._extract_drugs_with_llm(indication, search_text)

        # If web search yielded no drugs, fall back to LLM knowledge
        if not drugs:
            logger.info(f"Web search extracted 0 drugs, falling back to LLM knowledge")
            drugs = self.extract_drugs_from_knowledge(indication)

        return drugs

    async def _duckduckgo_search(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Perform a web search using DuckDuckGo HTML search.

        Args:
            query: Search query
            max_results: Maximum number of results to return

        Returns:
            List of search result dictionaries with 'title', 'url', 'snippet'
        """
        try:
            url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    data={"q": query},
                    headers=headers,
                    timeout=15.0,
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    logger.warning(f"DuckDuckGo search failed: {response.status_code}")
                    return []

                # Parse HTML response
                html = response.text
                results = self._parse_duckduckgo_html(html, max_results)
                logger.info(f"DuckDuckGo search found {len(results)} results for '{query[:50]}...'")
                return results

        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []

    def _parse_duckduckgo_html(self, html: str, max_results: int) -> List[Dict]:
        """Parse DuckDuckGo HTML search results."""
        results = []

        # Simple regex-based parsing for DuckDuckGo HTML results
        # Look for result links and snippets
        import re

        # Find result blocks (class="result__body")
        result_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]*)</a>.*?'
            r'<a[^>]*class="result__snippet"[^>]*>([^<]*(?:<[^>]*>[^<]*</[^>]*>)*[^<]*)</a>',
            re.DOTALL | re.IGNORECASE
        )

        # Alternative pattern for result snippets
        snippet_pattern = re.compile(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )

        title_pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )

        # Extract titles and URLs
        titles = title_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(titles[:max_results]):
            # Clean up the URL (DuckDuckGo wraps URLs)
            if "uddg=" in url:
                url_match = re.search(r'uddg=([^&]*)', url)
                if url_match:
                    from urllib.parse import unquote
                    url = unquote(url_match.group(1))

            # Clean HTML from title and snippet
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            snippet = snippets[i] if i < len(snippets) else ""
            snippet_clean = re.sub(r'<[^>]+>', '', snippet).strip()

            if title_clean:
                results.append({
                    "title": title_clean,
                    "url": url,
                    "snippet": snippet_clean,
                    "content": f"{title_clean}\n{snippet_clean}"
                })

        return results

    def _format_search_results(self, results: List[Dict]) -> str:
        """Format search results into text for LLM processing."""
        text_parts = []
        for i, result in enumerate(results[:10], 1):  # Limit to 10 results
            content = result.get("content", "")
            if content:
                # Truncate very long content
                if len(content) > 3000:
                    content = content[:3000] + "..."
                text_parts.append(f"Result {i}:\n{content}")

        return "\n\n---\n\n".join(text_parts)

    def extract_drugs_from_knowledge(self, indication: str) -> List[DrugCandidate]:
        """
        Extract FDA-approved drugs using LLM knowledge directly.

        This is a fallback when web search fails, using Claude's training data
        knowledge about FDA-approved drugs.

        Args:
            indication: Disease/condition name

        Returns:
            List of DrugCandidate objects
        """
        prompt = f"""List ALL FDA-approved brand name prescription drugs for: {indication}

Focus on innovative branded drugs (NDA/BLA approved), including:
- Biologics (monoclonal antibodies, fusion proteins, etc.)
- Small molecule targeted therapies
- Newer disease-modifying treatments

EXCLUDE: generics, biosimilars, OTC products, traditional non-targeted therapies

For each drug, provide:
- brand_name: Commercial brand name
- generic_name: Active ingredient
- manufacturer: Pharmaceutical company
- drug_class: Mechanism/therapeutic class

Respond with ONLY a JSON array:
[
    {{"brand_name": "DrugBrand", "generic_name": "druggeneric", "manufacturer": "Company", "drug_class": "Class"}},
    ...
]

Return empty array [] if no drugs are known."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()

            # Parse JSON
            if "```" in result_text:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_text)
                result_text = match.group(1) if match else result_text

            start = result_text.find("[")
            end = result_text.rfind("]") + 1
            if start >= 0 and end > start:
                result_text = result_text[start:end]

            drugs_data = json.loads(result_text)

            candidates = []
            for drug in drugs_data:
                brand_name = drug.get("brand_name", "")
                generic_name = drug.get("generic_name", "")

                # Skip excluded drugs
                if self._is_excluded_drug(brand_name, generic_name):
                    logger.debug(f"Skipping excluded drug: {brand_name} ({generic_name})")
                    continue

                candidate = DrugCandidate(
                    brand_name=brand_name,
                    generic_name=generic_name,
                    manufacturer=drug.get("manufacturer"),
                    application_number=None,
                    indications_text=f"FDA-approved for {indication}",
                    drug_type=self._infer_drug_type(drug.get("drug_class", "")),
                )
                if candidate.brand_name:
                    candidates.append(candidate)

            logger.info(f"LLM knowledge returned {len(candidates)} drugs for {indication}")
            return candidates

        except Exception as e:
            logger.error(f"LLM knowledge extraction failed: {e}")
            return []

    def _extract_drugs_with_llm(self, indication: str, search_results: str) -> List[DrugCandidate]:
        """Extract structured drug data from search results using LLM."""
        try:
            prompt = self.EXTRACTION_PROMPT.format(
                indication=indication,
                search_results=search_results[:15000],  # Limit total length
            )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text.strip()

            # Parse JSON
            if "```" in result_text:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result_text)
                result_text = match.group(1) if match else result_text

            # Find JSON array
            start = result_text.find("[")
            end = result_text.rfind("]") + 1
            if start >= 0 and end > start:
                result_text = result_text[start:end]

            drugs_data = json.loads(result_text)

            # Convert to DrugCandidate objects
            candidates = []
            for drug in drugs_data:
                brand_name = drug.get("brand_name", "")
                generic_name = drug.get("generic_name", "")

                # Skip excluded drugs
                if self._is_excluded_drug(brand_name, generic_name):
                    logger.debug(f"Skipping excluded drug: {brand_name} ({generic_name})")
                    continue

                candidate = DrugCandidate(
                    brand_name=brand_name,
                    generic_name=generic_name,
                    manufacturer=drug.get("manufacturer"),
                    application_number=None,
                    indications_text=f"FDA-approved for {indication}",
                    drug_type=self._infer_drug_type(drug.get("drug_class", "")),
                )
                if candidate.brand_name:
                    candidates.append(candidate)

            logger.info(f"Extracted {len(candidates)} drugs from web search for {indication}")
            return candidates

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    def _is_excluded_drug(self, brand_name: str, generic_name: str) -> bool:
        """Check if a drug should be excluded based on exclusion lists."""
        brand_lower = brand_name.lower() if brand_name else ""
        generic_lower = generic_name.lower() if generic_name else ""

        # Check exclusion list
        for excluded in EXCLUDED_DRUGS:
            if excluded in brand_lower or excluded in generic_lower:
                return True

        # Check if it's a known biosimilar brand
        if brand_lower in KNOWN_BIOSIMILAR_BRANDS:
            logger.debug(f"Excluding known biosimilar: {brand_name}")
            return True

        # Check biosimilar suffix pattern (generic name ends in -xxxx)
        if generic_lower and BIOSIMILAR_SUFFIX_PATTERN.match(generic_lower):
            logger.debug(f"Excluding biosimilar by suffix: {generic_name}")
            return True

        return False

    def _infer_drug_type(self, drug_class: str) -> Optional[str]:
        """Infer drug type from drug class description."""
        drug_class_lower = drug_class.lower()

        # Biologics
        biologic_terms = [
            "antibody", "mab", "il-", "interleukin", "biologic", "protein",
            "fusion", "receptor", "tnf", "cd", "pd-1", "pd-l1", "ctla",
            "vegf", "egfr", "her2", "bcma", "car-t", "gene therapy", "cell therapy"
        ]
        if any(term in drug_class_lower for term in biologic_terms):
            return "biologic"

        # Small molecules
        small_mol_terms = [
            "inhibitor", "kinase", "jak", "btk", "pde", "tyrosine",
            "agonist", "antagonist", "modulator", "blocker", "reuptake",
            "small molecule", "oral", "tablet"
        ]
        if any(term in drug_class_lower for term in small_mol_terms):
            return "small molecule"

        return None


class InnovativeDrugFinder:
    """
    Finds innovative drugs approved for an indication.

    Uses a multi-source strategy:
    1. MeSH standardization - get disease synonyms
    2. Database lookup - query drug_indications table
    3. Web search + LLM - extract drugs from web sources
    4. RxNorm deduplication - deduplicate by RxCUI
    5. Curated fallback - for major indications

    Filters out:
    - Generic drugs (ANDAs)
    - Biosimilars (identified by suffix or application type)
    - OTC products
    - Drugs from known generic manufacturers
    """

    def __init__(
        self,
        openfda_client: Optional[OpenFDAClient] = None,
        mesh_client: Optional[MeSHClient] = None,
        rxnorm_client: Optional[RxNormClient] = None,
        db_connection: Optional[DatabaseConnection] = None,
    ):
        """
        Initialize the service.

        Args:
            openfda_client: Optional OpenFDA client instance
            mesh_client: Optional MeSH client instance
            rxnorm_client: Optional RxNorm client instance
            db_connection: Optional database connection
        """
        self.openfda = openfda_client or OpenFDAClient()
        self.mesh = mesh_client or MeSHClient()
        self.rxnorm = rxnorm_client or RxNormClient()
        self.web_search = WebSearchDrugDiscovery()

        self._db = db_connection
        self._db_available = False

        # Try to connect to database
        try:
            if self._db is None:
                self._db = DatabaseConnection()
                self._db.connect()
            self._db_available = True
            logger.info("Database connection available for drug lookup")
        except Exception as e:
            logger.warning(f"Database not available: {e}")
            self._db_available = False

    async def find_innovative_drugs(
        self,
        indication: str,
        include_recently_approved: bool = True,
        max_results: int = 100,
    ) -> List[ApprovedDrug]:
        """
        Find all innovative drugs approved for the given indication.

        Args:
            indication: Disease/condition name (e.g., "atopic dermatitis")
            include_recently_approved: Include drugs approved in last 2 years
            max_results: Maximum results to process

        Returns:
            List of ApprovedDrug objects for innovative drugs only
        """
        logger.info(f"Searching for innovative drugs approved for: {indication}")
        indication_key = indication.strip().lower()

        all_found_drugs: Dict[str, ApprovedDrug] = {}  # rxcui or name -> drug

        # Step 1: Check curated list FIRST for well-known indications
        # This is the most reliable source for major therapeutic areas
        curated = INDICATION_DRUG_MAPPING.get(indication_key, [])
        if curated:
            logger.info(f"Step 1: Loading {len(curated)} drugs from curated list")
            for drug_info in curated:
                drug = ApprovedDrug(
                    drug_name=drug_info["brand"],
                    generic_name=drug_info["generic"],
                    manufacturer=drug_info.get("manufacturer"),
                    drug_type=drug_info.get("type"),
                )
                key = self._get_drug_key(drug)
                all_found_drugs[key] = drug

        # Step 2: MeSH standardization - get search terms
        logger.info("Step 2: MeSH standardization")
        mesh_data = self.mesh.get_disease_search_terms(indication)
        search_terms = mesh_data["search_terms"]
        logger.info(f"  MeSH terms: {search_terms[:5]}{'...' if len(search_terms) > 5 else ''}")

        # Step 3: Query internal database
        if self._db_available:
            logger.info("Step 3: Database query")
            db_drugs = self._query_database(search_terms)
            logger.info(f"  Found {len(db_drugs)} drugs in database")
            for drug in db_drugs:
                key = self._get_drug_key(drug)
                if key not in all_found_drugs:
                    all_found_drugs[key] = drug

        # Step 4: Web search + LLM extraction (for discovering newer drugs)
        logger.info("Step 4: Web search + LLM extraction")
        web_candidates = await self.web_search.search_drugs_for_indication(indication)
        logger.info(f"  Found {len(web_candidates)} drugs from web search")

        for candidate in web_candidates:
            # Skip biosimilars
            if self._is_biosimilar(candidate.brand_name, candidate.generic_name):
                logger.debug(f"  Skipping biosimilar from web: {candidate.brand_name}")
                continue
            drug = self._candidate_to_drug(candidate)
            key = self._get_drug_key(drug)
            if key not in all_found_drugs:
                all_found_drugs[key] = drug
                logger.debug(f"  Added from web: {drug.drug_name}")

        # Step 5: RxNorm deduplication
        logger.info("Step 5: RxNorm deduplication")
        deduplicated = self._deduplicate_with_rxnorm(list(all_found_drugs.values()))
        logger.info(f"  {len(deduplicated)} unique drugs after deduplication")

        logger.info(f"Total innovative drugs found for '{indication}': {len(deduplicated)}")
        return deduplicated

    def _query_database(self, search_terms: List[str]) -> List[ApprovedDrug]:
        """Query database for drugs matching any of the search terms."""
        if not self._db_available or not self._db:
            return []

        drugs = []
        seen_ids = set()

        try:
            with self._db.cursor() as cur:
                for term in search_terms[:10]:  # Limit to avoid too many queries
                    cur.execute("""
                        SELECT DISTINCT
                            d.drug_id, d.brand_name, d.generic_name, d.manufacturer,
                            d.drug_type, d.mechanism_of_action, d.approval_status,
                            d.dailymed_setid, d.rxcui
                        FROM drugs d
                        JOIN drug_indications i ON d.drug_id = i.drug_id
                        WHERE i.disease_name ILIKE %s
                          AND d.approval_status = 'approved'
                          AND d.drug_type IN ('biologic', 'small_molecule', 'mAb', 'fusion protein', 'protein')
                    """, (f'%{term}%',))

                    for row in cur.fetchall():
                        drug_id = row.get('drug_id')
                        if drug_id in seen_ids:
                            continue
                        seen_ids.add(drug_id)

                        brand_name = row.get('brand_name') or ''
                        generic_name = row.get('generic_name') or ''

                        # Skip generic manufacturers
                        manufacturer = (row.get('manufacturer') or '').lower()
                        if any(gm in manufacturer for gm in GENERIC_MANUFACTURERS):
                            continue

                        # Skip known biosimilars
                        if not self.is_innovative(brand_name, generic_name):
                            logger.debug(f"Skipping biosimilar from database: {brand_name}")
                            continue

                        drug = ApprovedDrug(
                            drug_name=brand_name or generic_name,
                            generic_name=generic_name,
                            manufacturer=row.get('manufacturer'),
                            drug_type=row.get('drug_type'),
                            mechanism_of_action=row.get('mechanism_of_action'),
                            dailymed_setid=row.get('dailymed_setid'),
                            rxcui=row.get('rxcui'),
                        )
                        drugs.append(drug)

        except Exception as e:
            logger.error(f"Database query failed: {e}")

        return drugs

    def _search_openfda(self, search_terms: List[str], max_results: int) -> List[DrugCandidate]:
        """Search OpenFDA for drugs with matching indications."""
        candidates = []
        seen_app_numbers = set()

        for term in search_terms[:5]:  # Limit search terms for efficiency
            # Try multiple search strategies since OpenFDA indexing is inconsistent
            search_queries = [
                f'indications_and_usage:"{term}"',  # Exact phrase in indications
                f'indications_and_usage:({term.replace(" ", "+AND+")})',  # AND search
            ]

            for search_query in search_queries:
                try:
                    params = self.openfda._add_api_key({
                        "search": search_query,
                        "limit": min(max_results, 100),
                    })

                    result = self.openfda.get("/drug/label.json", params=params)

                    if not result or "results" not in result:
                        continue

                    for label in result["results"]:
                        openfda_data = label.get("openfda", {})

                        # Must have brand name
                        brand_names = openfda_data.get("brand_name", [])
                        if not brand_names:
                            continue
                        brand_name = brand_names[0]

                        # Skip kits
                        if " kit" in brand_name.lower():
                            continue

                        # Must be NDA or BLA (not ANDA)
                        app_numbers = openfda_data.get("application_number", [])
                        if not app_numbers:
                            continue
                        app_number = app_numbers[0].upper()
                        if app_number.startswith("ANDA"):
                            continue

                        # Deduplicate by application number
                        if app_number in seen_app_numbers:
                            continue
                        seen_app_numbers.add(app_number)

                        # Skip biosimilars
                        if BIOSIMILAR_SUFFIX_PATTERN.match(brand_name.lower()):
                            continue

                        # Skip generic manufacturers
                        manufacturers = openfda_data.get("manufacturer_name", [])
                        manufacturer = manufacturers[0] if manufacturers else None
                        if manufacturer:
                            mfr_lower = manufacturer.lower()
                            if any(gm in mfr_lower for gm in GENERIC_MANUFACTURERS):
                                continue
                            if any(rp in mfr_lower for rp in COMPOUNDING_REPACKAGERS):
                                continue

                        # Get indications text
                        indications = label.get("indications_and_usage", [])
                        indications_text = indications[0] if indications else ""

                        # Infer drug type
                        drug_type = self.openfda.infer_drug_type(
                            openfda_data,
                            openfda_data.get("generic_name", [""])[0]
                        )

                        candidate = DrugCandidate(
                            brand_name=brand_name,
                            generic_name=openfda_data.get("generic_name", [None])[0],
                            manufacturer=manufacturer,
                            application_number=app_number,
                            indications_text=indications_text,
                            drug_type=drug_type,
                        )
                        candidates.append(candidate)

                except Exception as e:
                    logger.debug(f"OpenFDA search error for '{search_query}': {e}")

        return candidates

    def _candidate_to_drug(self, candidate: DrugCandidate) -> ApprovedDrug:
        """Convert a validated candidate to an ApprovedDrug."""
        return ApprovedDrug(
            drug_name=candidate.brand_name,
            generic_name=candidate.generic_name,
            manufacturer=candidate.manufacturer,
            application_number=candidate.application_number,
            drug_type=candidate.drug_type,
        )

    def _get_drug_key(self, drug: ApprovedDrug) -> str:
        """Get a unique key for a drug (for deduplication)."""
        # Prefer RxCUI if available
        if drug.rxcui:
            return f"rxcui:{drug.rxcui}"
        # Fall back to normalized generic name
        name = (drug.generic_name or drug.drug_name or "").lower()
        # Remove common suffixes
        name = re.sub(r'\s+(injection|tablet|capsule|cream|solution).*$', '', name, flags=re.IGNORECASE)
        return f"name:{name}"

    def _deduplicate_with_rxnorm(self, drugs: List[ApprovedDrug]) -> List[ApprovedDrug]:
        """Deduplicate drugs using RxNorm normalization."""
        if not drugs:
            return []

        seen_rxcui = set()
        seen_names = set()
        deduplicated = []

        for drug in drugs:
            # Try to get RxCUI if not already set
            rxcui = drug.rxcui
            if not rxcui:
                normalized = self.rxnorm.normalize_drug_name(
                    drug.generic_name or drug.drug_name
                )
                if normalized:
                    rxcui = normalized["rxcui"]
                    # Update drug with RxCUI
                    drug.rxcui = rxcui

            # Deduplicate
            if rxcui:
                if rxcui in seen_rxcui:
                    logger.debug(f"Skipping duplicate (RxCUI {rxcui}): {drug.drug_name}")
                    continue
                seen_rxcui.add(rxcui)
            else:
                # Fall back to name-based deduplication
                name_key = (drug.generic_name or drug.drug_name or "").lower()
                if name_key in seen_names:
                    logger.debug(f"Skipping duplicate (name): {drug.drug_name}")
                    continue
                seen_names.add(name_key)

            deduplicated.append(drug)

        return deduplicated

    def is_innovative(self, drug_name: str, generic_name: str = None) -> bool:
        """
        Check if a drug appears to be innovative (not biosimilar or generic).

        Args:
            drug_name: Brand name
            generic_name: Optional generic name

        Returns:
            True if appears to be an innovative drug
        """
        name_lower = drug_name.lower() if drug_name else ""
        generic_lower = generic_name.lower() if generic_name else ""

        # Check biosimilar brand name list
        if name_lower in KNOWN_BIOSIMILAR_BRANDS:
            return False

        # Check biosimilar suffix on generic name
        if generic_lower and BIOSIMILAR_SUFFIX_PATTERN.match(generic_lower):
            return False

        # Check biosimilar suffix on brand name
        if BIOSIMILAR_SUFFIX_PATTERN.match(name_lower):
            return False

        # Check for generic indicators in name
        if any(kw in name_lower for kw in ["generic", "biosimilar"]):
            return False

        return True

    def _is_biosimilar(self, brand_name: str, generic_name: str = None) -> bool:
        """Check if a drug is a biosimilar."""
        return not self.is_innovative(brand_name, generic_name)
