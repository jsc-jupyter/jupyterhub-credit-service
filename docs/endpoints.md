# API Endpoints

The **JupyterHub Credit Service** exposes API endpoints for reading credit data and, for administrators, adjusting it at runtime.  
All paths below are relative to the Hub, e.g. `/hub/api/credits`.

---

## User Endpoint

**Path:** `/hub/api/credits`  
**Method:** `GET`  
**Access:** Authenticated users  

Returns a list with one entry per credit configuration of the logged-in user. Each entry contains `name`, `balance`, `cap`, `grant_value`, `grant_interval` and `grant_last_update`. If the credit configuration belongs to a project, the entry also contains a nested `project` object with the same fields.

If the credit system is disabled, the endpoint returns `404`.

---

## Admin Endpoints

**Paths:** `/hub/api/credits/user/<user_name>/<credit_name>` and `/hub/api/credits/project/<project_name>`  
**Method:** `POST`  
**Access:** Requires the JupyterHub scope `admin:users`  

These endpoints allow administrators to adjust user or project credit configurations at runtime. The request body is JSON.

The user endpoint accepts:

- **balance**
- **cap**
- **grant_value**
- **grant_interval**
- **project**: a nested object with the optional keys `balance`, `cap`, `grant_value` and `grant_interval`, which updates the project attached to this credit configuration.

The project endpoint accepts `balance`, `cap`, `grant_value` and `grant_interval`.

A `balance` must not be negative and must not exceed the `cap`.

### Typical Use Case

If a user or project has exhausted their credits (for example, during a workshop or live session), an administrator can instantly grant additional credits to prevent interruptions.

### Examples

```bash
# Update user credit balance
curl -X POST -d '{"balance": 100}' \
     -H "Authorization: token $ADMIN_TOKEN" \
     https://_myhub_.com/hub/api/credits/user/user_name/credit_name

# Update the project of a user's credit configuration
curl -X POST -d '{"project": {"balance": 500}}' \
     -H "Authorization: token $ADMIN_TOKEN" \
     https://_myhub_.com/hub/api/credits/user/user_name/credit_name

# Update project credit balance
curl -X POST -d '{"balance": 1000, "cap": 1100}' \
     -H "Authorization: token $ADMIN_TOKEN" \
     https://_myhub_.com/hub/api/credits/project/project_name
```

---

## Endpoints used by the JupyterLab Hub Credit Extension

The following endpoints are used by the [JupyterLab Hub Credit Extension](https://github.com/jsc-jupyter/jupyterlab-hub-credit-extension) (`pip install jupyterlab_hub_credit_extension`), which shows the credit information of a running server inside JupyterLab. They are not meant to be called manually.

| Path | Method | Description |
| --- | --- | --- |
| `/hub/api/credits/sse` | `GET` | Server-sent events stream with the credit status of the logged-in user. Used by the Hub header, see [Frontend Integration](frontend.md). |
| `/hub/api/credits/sseserver/<user_name>[/<server_name>]` | `GET` | Server-sent events stream with balance and cap (and project) for one running server. The token may be sent in the `Authorization` header or as `token` query parameter, so servers accessed via API token are supported. Returns `409` if the server is not running. |
| `/hub/api/credits/stopserver/<user_name>[/<server_name>]` | `DELETE` | Stops a server. Requires the scope `access:servers`. |
| `/hub/api/credits/health` | `GET` | Returns `{"status": "ok"}` for authenticated requests. |