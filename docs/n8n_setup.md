# n8n setup: MCP server with exactly 3 tools (no send tool)

## 0. Google Doc
1. docs.google.com -> blank doc, name it **Weekly Log**.
2. Copy the ID from the address bar: the long part between `/d/` and `/edit`.

## 1. Token
Generate a long random token (this is the Bearer password):

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 2. Workflow
1. n8n -> **Create workflow** -> name it `ReviewPulse MCP`.
2. **Add first step** -> search **MCP Server Trigger** -> add it.
3. Authentication: **Bearer Auth** -> **Create new credential** -> paste the token -> Save.
4. Leave the path as is (or set `review-pulse`).

## 3. Tool 1: `append_to_doc`
1. On the trigger, click the **+** under **Tools** -> **Google Docs Tool**.
2. Credential: create **Google Docs OAuth2** and sign in.
3. Operation: **Update**. Document: **By ID**, **type your Doc ID** (fixed value, not an expression, not AI-filled).
4. Actions -> **Add** -> **Insert**. Text: hover the field and click **Let the model define this parameter**. Leave Index empty.
5. Rename the node **append_to_doc** (double-click the title). Description: `Append one weekly entry to the Weekly Log doc`.

## 4. Tool 2: `read_doc`
1. **+** under Tools -> **Google Docs Tool**. Operation: **Get**. Document: **By ID**, same fixed Doc ID.
2. Rename it **read_doc**. Description: `Read the Weekly Log doc (read only)`.

## 5. Tool 3: `create_email_draft`
1. **+** under Tools -> **Gmail Tool**. Credential: create **Gmail OAuth2** and sign in.
2. Resource: **Draft**. Operation: **Create**.
3. Subject and Message: **Let the model define this parameter**. Email Type: **Text**. Leave recipients empty.
4. Rename it **create_email_draft**. Description: `Create (never send) a Gmail draft`.

## 6. Publish and copy the URL
1. Do NOT add any Send node. The trigger should show exactly 3 tools.
2. Top right: **Publish** (the workflow must be active for the Production URL to work).
3. Open the MCP Server Trigger -> copy the **Production URL**.

## 7. .env
```
N8N_MCP_URL=<production URL>
N8N_MCP_TOKEN=<the token from step 1>
```

## 8. Test
```bash
venv\Scripts\python mcp_client.py
```
Expected: 3 tools listed and three PASS lines.
