import requests
import json
import os

POSTMAN_API_KEY = os.environ.get("POSTMAN_API_KEY")
WORKSPACE_ID = os.environ.get("WORKSPACE_ID")
BASE_URL = "https://api.getpostman.com"
SPEC_FILE = "specs/payment-refund-api-openapi.yaml"

# get all specs
def get_specs(workspace_id):
    url = f"{BASE_URL}/specs?workspaceId={workspace_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    return response.json().get("specs", [])

# get spec ID by name
def find_spec_id_by_name(specs, spec_name):
    """Find the spec ID for a given name."""
    for spec in specs:
        if spec["name"] == spec_name:
            print(f"Found spec '{spec_name}' and ID: {spec['id']}")
            return spec["id"]
    return None

# delete specs
def delete_spec(spec_id):
    url = f"{BASE_URL}/specs/{spec_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    return

# create a new spec
def create_spec(spec_name, spec_file, workspace_id):
    #Create a spec in Postman from a YAML file
    with open(spec_file, "r") as f:
        yaml_string = f.read()
    
    url = f"{BASE_URL}/specs?workspaceId={workspace_id}"

    payload = {
        "name": spec_name,
        "type": "OPENAPI:3.0",
        "files": [
            {
                "path": spec_file,
                "content": yaml_string
            }
        ]
    }
    headers = {
        "X-API-Key": POSTMAN_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))

    return response.json()

# generate the collection from the spec
def generate_collection(spec_id, name):
    url = f"{BASE_URL}/specs/{spec_id}/generations/collection"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    payload = {
        "name": name,
        "options": {
            "folderStrategy": "Paths",
            "enableOptionalParameters": True
        }
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.json()

if __name__ == "__main__":
    try:
        TARGET_SPEC_NAME = "Payment Processing API - Refund Service"
        print("Fetching existing specs")
        specs = get_specs(WORKSPACE_ID)
        print(specs)
        
        print("creating the spec")
        spec = create_spec(TARGET_SPEC_NAME, SPEC_FILE, WORKSPACE_ID)
        print(spec)

        specs = get_specs(WORKSPACE_ID)
        print(specs)

        spec_id = find_spec_id_by_name(specs, TARGET_SPEC_NAME)
        
        if spec_id:
        # 4. Generate collection for that spec
            generate_collection(spec_id, TARGET_SPEC_NAME + " Collection")

        print("Collection created successfully:")

    except Exception as e:
        print("Fatal error:", e)