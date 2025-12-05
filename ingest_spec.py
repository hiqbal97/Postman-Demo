import requests
import json
import os
import time
import glob
from pathlib import Path

def _load_env():
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        return
    except ImportError:
        pass

    env_path = ".env"
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)

_load_env()
try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

POSTMAN_API_KEY = os.environ.get("POSTMAN_API_KEY")
WORKSPACE_ID = os.environ.get("WORKSPACE_ID")
BASE_URL = "https://api.getpostman.com"
ENVIRONMENTS = {
    "Dev": "https://api-dev.payments.example.com/v2",
    "QA": "https://api-qa.payments.example.com/v2",
    "UAT": "https://api-uat.payments.example.com/v2",
    "Prod": "https://api.payments.example.com/v2",
}
JWT_CLIENT_CRED_PREREQ = [
    "// Pre-request script for JWT authentication via client credentials",
    "const clientId = pm.environment.get('client_id');",
    "const clientSecret = pm.environment.get('client_secret');",
    "const tokenUrl = pm.environment.get('token_url');",
    "",
    "const cachedToken = pm.environment.get('jwt_token');",
    "const tokenExpiry = pm.environment.get('token_expiry');",
    "if (cachedToken && tokenExpiry && Date.now() < tokenExpiry) {",
    "    pm.request.headers.upsert({ key: 'Authorization', value: `Bearer ${cachedToken}` });",
    "    return;",
    "}",
    "",
    "pm.sendRequest({",
    "    url: tokenUrl,",
    "    method: 'POST',",
    "    header: {",
    "        'Content-Type': 'application/x-www-form-urlencoded'",
    "    },",
    "    body: {",
    "        mode: 'urlencoded',",
    "        urlencoded: [",
    "            {key: 'grant_type', value: 'client_credentials'},",
    "            {key: 'client_id', value: clientId},",
    "            {key: 'client_secret', value: clientSecret}",
    "        ]",
    "    }",
    "}, (err, response) => {",
    "    if (err) {",
    "        console.error('Token request failed:', err);",
    "        return;",
    "    }",
    "",
    "    const jsonData = response.json();",
    "    const token = jsonData.access_token;",
    "    if (!token) {",
    "        console.error('No access_token in response');",
    "        return;",
    "    }",
    "    pm.environment.set('jwt_token', token);",
    "    pm.environment.set('token_expiry', Date.now() + (jsonData.expires_in * 1000));",
    "    pm.request.headers.upsert({ key: 'Authorization', value: `Bearer ${token}` });",
    "});",
]

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

# get spec id
def get_spec_id(spec_response):
    if not spec_response:
        return None
    if "spec" in spec_response and isinstance(spec_response["spec"], dict):
        return spec_response["spec"].get("id")
    return spec_response.get("id")

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


def get_generated_collections(spec_id):
    url = f"{BASE_URL}/specs/{spec_id}/generations/collection"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

# Try to pick the matching collection by name, else fall back to the first entry
def extract_collection(list_response, target_name=None):
    collections = list_response.get("collections") or []
    if target_name:
        for c in collections:
            if c.get("name") == target_name:
                return c.get("id") or c.get("uid")
    if collections:
        return collections[0].get("id") or collections[0].get("uid")
    return None

# adding wait time before trying to delete a collection
def wait_for_generated_collection(spec_id, target_name=None, attempts=10, delay_seconds=2):
    for attempt in range(1, attempts + 1):
        generated = get_generated_collections(spec_id)
        collection_id = extract_collection(generated, target_name)
        if collection_id:
            return collection_id
        if attempt < attempts:
            time.sleep(delay_seconds)
    return None

# list all the files within specs
def list_spec_files():
    return sorted(glob.glob("specs/**/*.y*ml", recursive=True))

# get the spec name from the yaml file
def get_spec_name(spec_file):
    spec_path = Path(spec_file)
    if yaml:
        try:
            with open(spec_file, "r") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    info = data.get("info") or {}
                    title = info.get("title")
                    if title:
                        return title
        except Exception:
            pass
    return spec_path.stem.replace("-", " ").title()

#set/overwrite the prerequest script
def check_prerequest_script(collection_id):
    set_prerequest_script(collection_id, JWT_CLIENT_CRED_PREREQ)

def list_specs(workspace_id):
    if not workspace_id:
        raise RuntimeError("WORKSPACE_ID is not set")
    url = f"{BASE_URL}/specs?workspaceId={workspace_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("specs", [])


def delete_spec(spec_id):
    url = f"{BASE_URL}/specs/{spec_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.delete(url, headers=headers)
    response.raise_for_status()

def list_collections(workspace_id):
    if not workspace_id:
        raise RuntimeError("WORKSPACE_ID is not set")
    url = f"{BASE_URL}/collections?workspaceId={workspace_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("collections", [])

def delete_collection(collection_id):
    url = f"{BASE_URL}/collections/{collection_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    requests.delete(url, headers=headers)

def get_collection(collection_id):
    url = f"{BASE_URL}/collections/{collection_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["collection"]

# attach/replace a prerequest script on the collection
def set_prerequest_script(collection_id, script_lines):
    collection = get_collection(collection_id)
    events = collection.get("event", [])
    events = [e for e in events if e.get("listen") != "prerequest"]
    events.append(
        {
            "listen": "prerequest",
            "script": {"type": "text/javascript", "exec": script_lines},
        }
    )
    collection["event"] = events

    url = f"{BASE_URL}/collections/{collection_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY, "Content-Type": "application/json"}
    payload = {"collection": collection}
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    return response.json()

def list_environments(workspace_id):
    if not workspace_id:
        raise RuntimeError("WORKSPACE_ID is not set")
    url = f"{BASE_URL}/environments?workspaceId={workspace_id}"
    headers = {"X-API-Key": POSTMAN_API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("environments", [])

# create the environments using the Postman API
def create_environment(name, base_url, workspace_id):
    if not workspace_id:
        raise RuntimeError("WORKSPACE_ID is not set")
    headers = {"X-API-Key": POSTMAN_API_KEY, "Content-Type": "application/json"}
    existing = list_environments(workspace_id)
    env_id = None
    for env in existing:
        if env.get("name") == name:
            env_id = env.get("id") or env.get("uid")
            break

    payload = {
        "environment": {
            "name": name,
            "values": [
                {"key": "baseUrl", "value": base_url, "enabled": True, "type": "default"}
            ],
        }
    }

    if env_id:
        url = f"{BASE_URL}/environments/{env_id}"
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return env_id

    url = f"{BASE_URL}/environments?workspaceId={workspace_id}"
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    env = response.json().get("environment", {})
    return env.get("id") or env.get("uid")

if __name__ == "__main__":
    try:
        if not POSTMAN_API_KEY:
            raise RuntimeError("POSTMAN_API_KEY is not set")
        if not WORKSPACE_ID:
            raise RuntimeError("WORKSPACE_ID is not set")

        print(f"Using workspace: {WORKSPACE_ID}")
        spec_files = list_spec_files()
        if not spec_files:
            raise RuntimeError("No spec files found under specs/")

        existing_collections = list_collections(WORKSPACE_ID)
        existing_specs = list_specs(WORKSPACE_ID)
        name_to_collection = {
            c.get("name"): (c.get("id") or c.get("uid"))
            for c in existing_collections
            if c.get("name")
        }
        for spec_file in spec_files:
            spec_name = get_spec_name(spec_file)
            collection_name = f"{spec_name} Collection"

            # delete older spec with same title
            for spec in existing_specs:
                if spec.get("name") == spec_name and spec.get("id"):
                    print(f"Deleting old spec '{spec_name}' ({spec.get('id')})")
                    delete_spec(spec.get("id"))
                    break

            print(f"Creating spec '{spec_name}' from {spec_file}")
            spec_response = create_spec(spec_name, spec_file, WORKSPACE_ID)
            spec_id = get_spec_id(spec_response)
            if not spec_id:
                raise RuntimeError(f"Could not extract spec ID from response: {spec_response}")

            print(f"Generating collection for spec {spec_id}")
            collection_response = generate_collection(spec_id, collection_name)
            print("Waiting for collection generation to complete...")
            collection_id = wait_for_generated_collection(spec_id, collection_name, attempts=15, delay_seconds=2)
            if not collection_id:
                raise RuntimeError(
                    f"Could not find collection ID. Generation POST response: {collection_response}"
                )

            print(f"Adding JWT client-credentials pre-request script to collection {collection_id}")
            check_prerequest_script(collection_id)

            if collection_name in name_to_collection and name_to_collection[collection_name] != collection_id:
                old_id = name_to_collection[collection_name]
                print(f"Deleting old collection '{collection_name}' ({old_id}) and keeping new {collection_id}")
                time.sleep(2)
                delete_collection(old_id)
            name_to_collection[collection_name] = collection_id

        print("Creating/updating environments for base URLs")
        for env_name, base_url in ENVIRONMENTS.items():
            env_id = create_environment(env_name, base_url, WORKSPACE_ID)
            print(f" - {env_name} environment ready (id: {env_id}) with base_url={base_url}")

        print("Collections created and environments updated.")

    except Exception as e:
        print("Fatal error:", e)
