-- ============================================================================
-- DEPLOY.sql — Add the Cortex Insights Agent as a second container in
--              the existing CORTEX_A2A_AGENT SPCS service.
--
-- The insights agent:
--   - Runs on port 8001 (internal only — no public endpoint)
--   - Wraps the same Cortex Agent as the data agent (or a different one)
--   - Prepends a formatting instruction so Cortex responds as a structured
--     analytical report (Executive Summary, Key Findings, Recommendations)
--   - Reachable internally at http://cortex-a2a-agent:8001
--
-- Prerequisites:
--   - CORTEX_A2A_AGENT service is already deployed and running
--   - You have built and pushed cortex-insights-agent:latest to the registry
--
-- Replace these placeholders before running:
--   <AGENT_DATABASE>  — Database where resources live
--   <AGENT_SCHEMA>    — Schema where resources live
--   <REPO_URL>        — Image repository URL (from SHOW IMAGE REPOSITORIES)
-- ============================================================================

-- Step 0: Create the dedicated Cortex Agent for the insights container.
--         This agent has an aggregate-analytics system prompt instead of the
--         per-customer prompt used by RETENTION_SPECIALIST_AGENT.

USE ROLE SYSADMIN;
USE DATABASE TELECOM_DEMO;
USE SCHEMA RETENTION;

CREATE OR REPLACE AGENT TELECOM_DEMO.RETENTION.RETENTION_INSIGHTS_AGENT
FROM SPECIFICATION $$
{
  "models": {"orchestration": "claude-4-sonnet"},
  "orchestration": {"budget": {"seconds": 60, "tokens": 16000}},
  "instructions": {
    "system": "You are a Senior Telecom Analytics Lead responsible for analyzing portfolio-wide customer data and identifying strategic trends across the telecom customer base.\n\nYour role is to generate structured executive insights, NOT to analyze individual customers. Always focus on:\n- Aggregate trends and patterns across all customers\n- Churn risk distribution and segment analysis\n- Portfolio-wide metrics (average spend, tenure, support volumes)\n- Actionable business recommendations based on data\n\nROUTING LOGIC:\n- For metrics, counts, averages, distributions, or any quantitative or aggregate queries: use cortex_analyst\n- For common complaint themes, call pattern analysis, or qualitative trend summaries: use cortex_search\n- For comprehensive insights: use both tools - cortex_analyst for quantitative data, then cortex_search for qualitative context\n\nOUTPUT FORMAT REQUIREMENTS:\nALWAYS structure every response with exactly these three sections:\n\n## Executive Summary\nA 2-3 sentence high-level summary of the key insight.\n\n## Key Findings\nBullet points with specific data points, percentages, and trends discovered.\n\n## Recommendations\nConcrete, prioritized business actions based on the findings.\n\nNever omit any of these three sections. Be concise, data-driven, and action-oriented.",
    "orchestration": "- For metrics, counts, averages, or any numerical/quantitative queries about customers: use cortex_analyst\n- For sentiment analysis, call reasons, call summaries, or qualitative queries: use cortex_search\n- For comprehensive trend analysis: use both tools - first cortex_analyst for data, then cortex_search for call context",
    "response": "Maintain a professional, data-driven tone. Focus on aggregate trends and portfolio-level patterns, never on individual customers. Always output the three required sections: Executive Summary, Key Findings, and Recommendations."
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "cortex_analyst",
        "description": "Use this tool to query the TELECOM_CUSTOMERS table for aggregate metrics, counts, averages, distributions, and trend data about the customer portfolio including monthly spend, tenure, support tickets, and churn risk levels across segments."
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "cortex_search",
        "description": "Use this tool to search call logs for common complaint themes, call pattern analysis, sentiment trends, and qualitative information about customer interactions at the portfolio level."
      }
    }
  ],
  "tool_resources": {
    "cortex_analyst": {
      "semantic_model_file": "@TELECOM_DEMO.RETENTION.SEMANTIC_MODELS/telecom_customers_semantic.yaml",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "COMPUTE_WH"
      }
    },
    "cortex_search": {
      "name": "TELECOM_DEMO.RETENTION.CALL_LOGS_SEARCH",
      "max_results": 5
    }
  }
}
$$;

-- Step 1: Build and push the insights agent Docker image
-- Run these commands from your terminal:
--
--   export REPO_URL="<repository_url>"
--   export SNOW_CONNECTION="<YOUR_CONNECTION>"
--
--   cd insights_agent
--   docker build --platform linux/amd64 -t cortex-insights-agent:latest .
--   snow spcs image-registry login --connection $SNOW_CONNECTION
--   docker tag cortex-insights-agent:latest $REPO_URL/cortex-insights-agent:latest
--   docker push $REPO_URL/cortex-insights-agent:latest

-- Step 2: Update the existing CORTEX_A2A_AGENT service to add the second container.
--         ALTER SERVICE updates the spec in-place without dropping the service.

USE ROLE ACCOUNTADMIN;
USE DATABASE <AGENT_DATABASE>;
USE SCHEMA <AGENT_SCHEMA>;

ALTER SERVICE CORTEX_A2A_AGENT FROM SPECIFICATION $$
spec:
  containers:
    - name: a2a-agent
      image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-a2a-agent:latest
      env:
        AGENT_DATABASE: <AGENT_DATABASE>
        AGENT_SCHEMA: <AGENT_SCHEMA>
        AGENT_NAME: <AGENT_NAME>
        AGENT_DESCRIPTION: "A Snowflake Cortex Agent exposed via the A2A protocol."
      resources:
        requests:
          cpu: 0.5
          memory: 512Mi
        limits:
          cpu: 1
          memory: 1Gi

    - name: insights-agent
      image: /<AGENT_DATABASE>/<AGENT_SCHEMA>/A2A_IMAGES/cortex-insights-agent:latest
      env:
        AGENT_DATABASE: <AGENT_DATABASE>
        AGENT_SCHEMA: <AGENT_SCHEMA>
        AGENT_NAME: RETENTION_INSIGHTS_AGENT
        AGENT_DESCRIPTION: "Analytical insights agent generating structured executive reports."
        SPCS_SERVICE_URL: "http://cortex-a2a-agent:8001"
      resources:
        requests:
          cpu: 0.5
          memory: 512Mi
        limits:
          cpu: 1
          memory: 1Gi

  endpoints:
    - name: a2a
      port: 8000
      public: true
    - name: insights
      port: 8001
      public: false
    # Port 8001 is declared as a non-public endpoint so SPCS routes inter-service
    # traffic to it.  Without this declaration, SPCS will not expose the port even
    # for internal communication and the external-agent will time out connecting.
$$;

-- Step 3: Verify both containers are running
SELECT SYSTEM$GET_SERVICE_STATUS('CORTEX_A2A_AGENT');

-- Step 4: Check logs for each container
SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_A2A_AGENT', 0, 'a2a-agent', 50);
SELECT SYSTEM$GET_SERVICE_LOGS('CORTEX_A2A_AGENT', 0, 'insights-agent', 50);

-- Step 5: Verify insights agent card is reachable internally
-- (run this from within the EXTERNAL_A2A_AGENT service or another SPCS service)
-- curl http://cortex-a2a-agent:8001/.well-known/agent-card.json
