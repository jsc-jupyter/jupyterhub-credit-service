# API Endpoints

The **JupyterHub Credit Service** exposes two main API endpoints for interacting with user and project credit data.  
These endpoints allow both users and administrators to monitor and manage credit balances in real time.

---

## User Endpoint

**Path:** `/hub/api/credits`  
**Access:** Authenticated users  

This endpoint returns the current credit status of the logged-in user, including available balance, cap, and any associated project information.

---

## Admin Endpoint

**Path:** `/hub/api/credits/user/<user_name>` / `/hub/api/credits/project/<project_name>`  
**Access:** Administrators only  

This endpoint allows administrators to adjust user or project credit configurations at runtime.  
Admin users can update values such as:

- **balance**  
- **cap**  
- **grant_value**  
- **grant_interval**  
- **project_name**

### Typical Use Case

If a user or project has exhausted their credits (for example, during a workshop or live session), an administrator can instantly grant additional credits to prevent interruptions.

### Examples

```bash
# Update user credit balance
curl -X POST -d '{"balance": 100}' \
     -H "Authorization: token $ADMIN_TOKEN" \
     https://_myhub_.com/hub/api/credits/user/user_name

# Update project credit balance
curl -X POST -d '{"balance": 1000, "cap": 1100}' \
     -H "Authorization: token $ADMIN_TOKEN" \
     https://_myhub_.com/hub/api/credits/project/project_name
```