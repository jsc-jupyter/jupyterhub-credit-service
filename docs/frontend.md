# Frontend Integration

The **JupyterHub Credit Service** integrates smoothly with the standard JupyterHub frontend, allowing users to view their current credit balance directly in the interface.  
If you're using a customized JupyterHub frontend, you can easily include the same functionality. Just check out the changes shown below.

```python
from jupyterhub_credit_service import template_paths
c.JupyterHub.template_paths = template_paths
```

This configuration automatically inserts the user's credit balance into the JupyterHub header.
Whenever credits are updated on the server, the displayed balance updates in real time - no manual page refresh required.

<div style="text-align: center;">
  <img src="https://jsc-jupyter.github.io/jupyterhub-credit-service/images/image_home.png" alt="JupyterHub" style="width: 100%;">
</div>

<summary>Click here to see the frontend changes of JupyterHub<details>
```bash
diff -Naur jupyterhub/page.html jupyterhub_credit_service/page.html
--- jupyterhub/page.html        2025-10-20 09:03:45.337461368 +0200
+++ jupyterhub_credit_service/page.html 2025-10-20 09:03:30.204356558 +0200
@@ -97,6 +97,46 @@                                     
         xsrf_token: "{{ xsrf_token }}",
       }; 
        
+      {# Connect to CreditsSSEAPIHandler #}
+      {%- if user %}
+      var creditsEvtSource = undefined;
+      function creditsSSEInit() {
+        let sseUrl = `${jhdata.base_url}api/credits/sse`
+        if ( jhdata.user ) {
+            sseUrl = `${jhdata.base_url}api/credits/sse?_xsrf=${window.jhdata.xsrf_token}`;
+        }                                   
+        if ( creditsEvtSource ) {            
+          creditsEvtSource.close();
+        }                            
+        creditsEvtSource = new EventSource(sseUrl);
+        creditsEvtSource.onmessage = (e) => {
+          try {                                                                                                              
+            const jsonData = JSON.parse(event.data);
+            var htmlText = `Credits: ${jsonData.balance}/${jsonData.cap}`;
+            if ( jsonData.project ) {
+              htmlText += ` (${jsonData.project.name}: ${jsonData.project.balance} / ${jsonData.project.cap})`;
+            }                                 
+            const span = document.getElementById("credits-user");                                       
+            span.innerHTML = htmlText;
+          } catch (error) {
+              console.error("Failed to parse SSE data:", error);
+          }
+        };
+        creditsEvtSource.onerror = (e) => {
+          console.log("Reconnect Credits EventSource");
+          // Reconnect
+        }
+      }
+      $(document).ready(function() {
+        creditsSSEInit();
+      });
+      window.onbeforeunload = function() {
+        if (typeof creditsEvtSource !== 'undefined') {
+            creditsEvtSource.close();
+        }
+      }
+      {%- endif %}
+
 </script>
     {# djlint: on #}
     {% block meta %}
@@ -174,6 +214,13 @@
             </ul>
             <ul class="nav navbar-nav me-2">
               {% block nav_bar_right_items %}
+                {% if user %}
+                <li class="nav-item">
+                  <span id="credits-user"
+                        class="me-2"
+                        style="display: flex; align-items: center;"/>
+                </li>
+                {% endif %}
                 <li class="nav-item">
                   {% block theme_toggle %}
                     <button class="btn btn-sm"
```
</details></summary>