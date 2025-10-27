import requests
from bs4 import BeautifulSoup
import re
from flask import Flask, request, jsonify
import os

# Flask app setup
app = Flask(__name__)

# Configuration
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
    "Referer": "https://vahanx.in/",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br"
}

# Desired order for output (inspired by second script)
DESIRED_ORDER = [
    "Owner Name", "Father's Name", "Owner Serial No", "Model Name", "Maker Model",
    "Vehicle Class", "Fuel Type", "Fuel Norms", "Registration Date", "Insurance Company",
    "Insurance No", "Insurance Expiry", "Insurance Upto", "Fitness Upto", "Tax Upto",
    "PUC No", "PUC Upto", "Financier Name", "Registered RTO", "Address", "City Name", "Phone"
]

# Enhanced vehicle info scraper
def get_comprehensive_vehicle_details(rc_number: str) -> dict:
    """Fetch comprehensive vehicle details from vahanx.in."""
    rc = rc_number.strip().upper()
    url = f"https://vahanx.in/rc-search/{rc}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to fetch data: {str(e)}", "By": "@ZenDesh"}

    # Helper function to extract card values
    def extract_card(label):
        for div in soup.select(".hrcd-cardbody"):
            span = div.find("span")
            if span and label.lower() in span.text.lower():
                p = div.find("p")
                return p.get_text(strip=True) if p else None
        return None

    # Helper function to extract from sections
    def extract_from_section(header_text, keys):
        section = soup.find("h3", string=lambda s: s and header_text.lower() in s.lower())
        section_card = section.find_parent("div", class_="hrc-details-card") if section else None
        result = {}
        for key in keys:
            span = section_card.find("span", string=lambda s: s and key in s) if section_card else None
            if span:
                val = span.find_next("p")
                result[key.lower().replace(" ", "_")] = val.get_text(strip=True) if val else None
        return result

    # Generic value extractor
    def get_value(label):
        try:
            div = soup.find("span", string=label)
            if div:
                div = div.find_parent("div")
                p = div.find("p") if div else None
                return p.get_text(strip=True) if p else None
        except:
            return None

    # Extract registration number
    try:
        registration_number = soup.find("h1").text.strip()
    except:
        registration_number = rc

    # Extract main card details
    modal_name = extract_card("Modal Name") or get_value("Model Name")
    owner_name = extract_card("Owner Name") or get_value("Owner Name")
    code = extract_card("Code")
    city = extract_card("City Name") or get_value("City Name")
    phone = extract_card("Phone") or get_value("Phone")
    website = extract_card("Website")
    address = extract_card("Address") or get_value("Address")

    # Extract sections
    ownership = extract_from_section("Ownership Details", ["Owner Name", "Father's Name", "Owner Serial No", "Registered RTO"])
    vehicle = extract_from_section("Vehicle Details", ["Model Name", "Maker Model", "Vehicle Class", "Fuel Type", "Fuel Norms", "Cubic Capacity", "Seating Capacity"])
    insurance = extract_from_section("Insurance Information", ["Insurance Company", "Insurance No", "Insurance Expiry", "Insurance Upto"])
    validity = extract_from_section("Important Dates", ["Registration Date", "Vehicle Age", "Fitness Upto", "Insurance Upto", "Tax Upto"])
    puc = extract_from_section("PUC Details", ["PUC No", "PUC Upto"])
    other = extract_from_section("Other Information", ["Financer Name", "Financier Name", "Permit Type", "Blacklist Status", "NOC Details"])

    # Insurance status
    insurance_expired_box = soup.select_one(".insurance-alert-box.expired .title")
    expired_days = None
    if insurance_expired_box:
        match = re.search(r"(\d+)", insurance_expired_box.text)
        expired_days = int(match.group(1)) if match else None
    insurance_status = "Expired" if expired_days else "Active"

    # Compile data
    data = {
        "registration_number": registration_number,
        "status": "success",
        "basic_info": {
            "model_name": modal_name,
            "owner_name": owner_name,
            "fathers_name": get_value("Father's Name") or ownership.get("father's_name"),
            "code": code,
            "city": city,
            "phone": phone,
            "website": website,
            "address": address
        },
        "ownership_details": {
            "owner_name": ownership.get("owner_name") or owner_name,
            "fathers_name": ownership.get("father's_name"),
            "serial_no": ownership.get("owner_serial_no"),
            "rto": ownership.get("registered_rto")
        },
        "vehicle_details": {
            "maker": vehicle.get("model_name") or modal_name,
            "model": vehicle.get("maker_model"),
            "vehicle_class": vehicle.get("vehicle_class"),
            "fuel_type": vehicle.get("fuel_type"),
            "fuel_norms": vehicle.get("fuel_norms"),
            "cubic_capacity": vehicle.get("cubic_capacity"),
            "seating_capacity": vehicle.get("seating_capacity")
        },
        "insurance": {
            "status": insurance_status,
            "company": insurance.get("insurance_company"),
            "policy_number": insurance.get("insurance_no"),
            "expiry_date": insurance.get("insurance_expiry"),
            "valid_upto": insurance.get("insurance_upto"),
            "expired_days_ago": expired_days
        },
        "validity": {
            "registration_date": validity.get("registration_date"),
            "vehicle_age": validity.get("vehicle_age"),
            "fitness_upto": validity.get("fitness_upto"),
            "insurance_upto": validity.get("insurance_upto"),
            "tax_upto": validity.get("tax_upto")
        },
        "puc_details": {
            "puc_number": puc.get("puc_no"),
            "puc_valid_upto": puc.get("puc_upto")
        },
        "other_info": {
            "financer": other.get("financer_name") or other.get("financier_name"),
            "permit_type": other.get("permit_type"),
            "blacklist_status": other.get("blacklist_status"),
            "noc": other.get("noc_details")
        },
        "By": "@ZenDesh"
    }

    # Remove None values and empty strings
    def clean_dict(d):
        if isinstance(d, dict):
            return {k: clean_dict(v) for k, v in d.items() if v is not None and v != ""}
        return d
    
    return clean_dict(data)

# Flask API routes
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "Vehicle Information API",
        "version": "2.0",
        "endpoints": {
            "vehicle_info": "/api/vehicle-info?rc=<RC_NUMBER>",
            "lookup": "/lookup?rc=<RC_NUMBER>",
            "health": "/health"
        },
        "example": f"https://rcdetail.onrender.com/api/vehicle-info?rc=DL01AB1234",
        "By": "@ZenDesh"
    })

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "api": "active",
        "timestamp": time.time(),
        "By": "@ZenDesh"
    })

@app.route("/api/vehicle-info", methods=["GET"])
def get_vehicle_info():
    rc = request.args.get("rc")
    if not rc:
        return jsonify({"error": "Missing rc parameter", "usage": "/api/vehicle-info?rc=<RC_NUMBER>", "By": "@ZenDesh"}), 400
    try:
        data = get_comprehensive_vehicle_details(rc)
        if data.get("error"):
            return jsonify(data), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "By": "@ZenDesh"}), 500

@app.route("/lookup", methods=["GET"])
def lookup_vehicle():
    rc = request.args.get("rc")
    if not rc:
        return jsonify({"error": "Please provide ?rc= parameter", "By": "@ZenDesh"}), 400
    
    rc = rc.strip().upper()
    url = f"https://vahanx.in/rc-search/{rc}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Network error: {str(e)}", "By": "@ZenDesh"}), 400

    data = {}
    for key in DESIRED_ORDER:
        try:
            div = soup.find("span", string=key)
            if div:
                div = div.find_parent("div")
                p = div.find("p") if div else None
                data[key] = p.get_text(strip=True) if p else None
        except AttributeError:
            data[key] = None

    ordered_details = {key: data[key] for key in DESIRED_ORDER if data.get(key)}
    ordered_details["By"] = "@ZenDesh"
    return jsonify(ordered_details)

# Run app for local development
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
