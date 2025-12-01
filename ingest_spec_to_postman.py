#!/usr/bin/env python3
"""
ingest_spec_to_postman.py
Usage:
  python ingest_spec_to_postman.py --api-key $POSTMAN_API_KEY --workspace-id $WORKSPACE_ID --spec-file payment-refund-api-openapi.yaml --output-dir ./generated
"""

import argparse
import json
import os
import sys
import time
import requests

BASE_URL = "https://api.getpostman.com"
HEADERS_TEMPLATE = {
    "X-Api-Key": None,
    "Content-Type": "application/json"
}

def pretty(msg): print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def create_spec(api_key, workspace_id, spec_file, spec_name=None, content_type="yaml"):
    with open(spec_file, "r", encoding="utf-8") as f:
        content = f.read()
    payload = {
        "spec": {
            "name": spec_name or os.path.basename(spec_file),
            "content": content,
            "contentType": content_type
        }
    }
    headers = HEADERS_TEMPLATE.copy()
    headers["X-Api-Key"] = api_key
    pretty(f"Uploading spec '{payload['spec']['name']}' to workspace {workspace_id}...")
    r = requests.post(f"{BASE_URL}/specs?workspaceId={workspace_id}", headers=headers, json=payload)
    r.raise_for_status()
    spec = r.json()["spec"]
    pretty(f"Created spec: {spec['id']}")
    return spec["id"]

def generate_collection(api_key, spec_id, options=None):
    headers = HEADERS_TEMPLATE.copy()
    headers["X-Api-Key"] = api_key
    payload = {"options": options or {"requestParametersResolution": "example", "exampleParametersResolution": "example"}}
    pretty(f"Requesting collection generation for spec {spec_id} ...")
    r = requests.post(f"{BASE_URL}/specs/{spec_id}/generations/collection", headers=headers, json=payload)
    r.raise_for_status()
    col = r.json().get("collection")
    if not col:
        raise RuntimeError("No collection returned from generation endpoint")
    pretty(f"Generated collection: {col['id']}")
    return col["id"]

def export_collection(api_key, collection_id, out_dir):
    headers = HEADERS_TEMPLATE.copy()
    headers["X-Api-Key"] = api_key
    pretty(f"Exporting collection {collection_id} ...")
    r = requests.get(f"{BASE_URL}/collections/{collection_id}", headers=headers)
    r.raise_for_status()
    data = r.json()
    out_path = os.path.join(out_dir, f"collection-{collection_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    pretty(f"Exported collection to {out_path}")
    return out_path

def create_environment(api_key, workspace_id, env_name, values):
    headers = HEADERS_TEMPLATE.copy()
    headers["X-Api-Key"] = api_key
    payload = {
        "environment": {
            "name": env_name,
            "values": [{"key": k, "value": v, "enabled": True} for k, v in values.items()]
        }
    }
    pretty(f"Creating environment '{env_name}' in workspace {workspace_id} ...")
    r = requests.post(f"{BASE_URL}/workspaces/{workspace_id}/environments", headers=headers, json=payload)
    r.raise_for_status()
    env = r.json().get("environment")
    pretty(f"Created environment: {env.get('id')}")
    return env.get("id")

def attach_pre_request_script_to_collection(api_key, collection_id, script_content):
    # Simple approach: GET collection, patch the item-level event at top-level
    headers = HEADERS_TEMPLATE.copy()
    headers["X-Api-Key"] = api_key
    r = requests.get(f"{BASE_URL}/collections/{collection_id}", headers=headers)
    r.raise_for_status()
    payload = r.json()["collection"]
    # Ensure events list exists
    if "event" not in payload:
        payload["event"] = []
    payload["event"].append({
        "listen": "prerequest",
        "script": {
            "type": "text/javascript",
            "exec": script_content.splitlines()
        }
    })
    pretty("Updating collection to add a pre-request script (JWT)...")
    r = requests.put(f"{BASE_URL}/collections/{collection_id}", headers=headers, json={"collection": payload})
    r.raise_for_status()
    pretty("Attached pre-request script to collection.")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--spec-file", required=True)
    parser.add_argument("--output-dir", default="./generated")
    parser.add_argument("--spec-name", default=None)
    parser.add_argument("--content-type", default="yaml", choices=["yaml", "json"])
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    try:
        spec_id = create_spec(args.api_key, args.workspace_id, args.spec_file, spec_name=args.spec_name, content_type=args.content_type)
        collection_id = generate_collection(args.api_key, spec_id)
        collection_file = export_collection(args.api_key, collection_id, args.output_dir)

        # Create sample environments
        envs = {
            "dev": {"base_url": "https://dev.api.company/payments", "client_id": "{{DEV_CLIENT_ID}}", "client_secret": "{{DEV_CLIENT_SECRET}}", "token_url": "https://auth.dev.company/oauth2/token"},
            "qa":  {"base_url": "https://qa.api.company/payments",  "client_id": "{{QA_CLIENT_ID}}",  "client_secret": "{{QA_CLIENT_SECRET}}",  "token_url": "https://auth.qa.company/oauth2/token"},
            "uat": {"base_url": "https://uat.api.company/payments", "client_id": "{{UAT_CLIENT_ID}}", "client_secret": "{{UAT_CLIENT_SECRET}}", "token_url": "https://auth.uat.company/oauth2/token"},
            "prod":{"base_url": "https://api.company/payments",     "client_id": "{{PROD_CLIENT_ID}}", "client_secret": "{{PROD_CLIENT_SECRET}}", "token_url": "https://auth.company/oauth2/token"}
        }
        created_envs = {}
        for name, vals in envs.items():
            created_envs[name] = create_environment(args.api_key, args.workspace_id, f"Payment Refund - {name.upper()}", vals)

        # Template JWT pre-request script (short)
        jwt_script = """
// JWT pre-request script (auto-refresh)
const tokenUrl = pm.environment.get("token_url");
const clientId = pm.environment.get("client_id");
const clientSecret = pm.environment.get("client_secret");
const cachedToken = pm.environment.get("jwt_token");
const expiry = parseInt(pm.environment.get("token_expiry") || "0", 10);

if (cachedToken && expiry && Date.now() < expiry) {
    // token still valid
} else {
    pm.sendRequest({
        url: tokenUrl,
        method: 'POST',
        header: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: {
            mode: 'urlencoded',
            urlencoded: [
                {key:'grant_type', value:'client_credentials'},
                {key:'client_id', value: clientId},
                {key:'client_secret', value: clientSecret}
            ]
        }
    }, function (err, res) {
        if (err) { console.error(err); return; }
        const j = res.json();
        pm.environment.set("jwt_token", j.access_token);
        pm.environment.set("token_expiry", Date.now() + (j.expires_in * 1000) - 5000);
    });
}
"""
        attach_pre_request_script_to_collection(args.api_key, collection_id, jwt_script)

        pretty("Done. Files generated in: " + os.path.abspath(args.output_dir))
        pretty(f"Spec ID: {spec_id}  |  Collection ID: {collection_id}")
    except Exception as e:
        pretty("ERROR: " + str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
