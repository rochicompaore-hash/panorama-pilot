#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: >-
  Resume Panorama Pilot from the real repository on dev/cashflow-reliability-preview,
  verify the overdue-receivable forecast correction, and provide a private review preview.
backend:
  - task: "Cash forecast excludes overdue and untrustworthy collection dates"
    implemented: true
    working: true
    file: "backend/app/services/cfo_engine.py; backend/app/services/cash_engine.py; backend/app/models_ops.py; backend/app/routers/sales_orders.py; backend/app/routers/logistics.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: >-
          Verified baseline 2b3fef7 includes overdue receivables in today's inflows.
          Backend correction in progress: common forecast eligibility, exclusions,
          coherent daily/weekly/horizon totals, certified balance versus updated estimate.
      - working: true
        agent: "testing"
        comment: >-
          2026-10-23: 71 isolated tests passed in 1.04 seconds using the repository's
          configured two pytest-xdist workers. This comprises 40 new cash-flow regression
          cases, 20 operational-event/helper/handler cases, and 11 existing pure tests.
          Verified overdue claims remain visible but never become assumed inflows;
          unreliable dates fail closed; all horizons agree with daily and 13-week series;
          overdue payables remain immediate; future actuals do not affect current cash;
          uncertified/partial balances and mixed certification dates block forecasts.
          Real sales-order and logistics handlers were invoked with local DB/auth doubles:
          genuine transitions record timestamps, existing timestamps survive, and note edits,
          repeated transitions, and resubmitted reports never manufacture historical dates.
          Five existing live MongoDB/HTTP integration tests were explicitly excluded.
          No production API, database, credentials, or real financial data were used.
frontend:
  - task: "Show planned collections and excluded overdue receivables accurately"
    implemented: true
    working: true
    file: "frontend/src/components/cfo/CashCommandCenter.jsx; frontend/src/components/cfo/CfoControlTower.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: >-
          Frontend copy and an exported pure dashboard view are being prepared.
          The private preview will use the actual view and synthetic Python-engine outputs.
      - working: true
        agent: "main"
        comment: >-
          2026-10-23: Both modified JSX modules compiled independently with esbuild and
          the isolated preview production build passed. Browser verification exercised
          all four synthetic scenarios: overdue receivables, uncertified bank balance,
          missing collection dates, and the day-90/day-91 horizon boundary. The preview
          imports the actual CashCommandCenterView and data generated by the actual
          Python engine against read-only in-memory fixtures. Checked the final build's
          labels, 1000 reserve, excluded-receivable breakdown, null forecast gate, all
          91 daily points, and the 7800 final 13-week position. Desktop screenshot
          inspected with no visible clipping. Initial Recharts size warnings settled
          after layout; no app runtime error observed. No mobile-device, full-app build,
          live API, real database, or production integration verification is claimed.
metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 3
  run_ui: true
test_plan:
  current_focus:
    - "Overdue receivables excluded from all inflow forecasts but retained in receivables and collection priority"
    - "Invalid/missing/past collection dates and undated operational triggers fail closed"
    - "Daily, 13-week, horizon, stress, quality, and monthly calculations agree"
    - "Overdue outflows remain immediate; certified-cash gate and actual-date bounds remain valid"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"
agent_communication:
  - agent: "main"
    message: >-
      Use isolated local tests only, no production HTTP endpoints or databases and no live
      credentials. Add independent regression cases and adapt legacy assertions that encode
      the corrected bug. Report exact tests run and any unverified integration limits.
  - agent: "testing"
    message: >-
      Backend verification complete; frontend/browser verification belongs to the main agent.
      Reproduce from backend/ with ../.venv/bin/python -m pytest -q
      tests/test_cashflow_reliability.py tests/test_cashflow_event_timestamps.py
      tests/test_cash_command_center_v1.py tests/test_cfo_control_tower_v1.py
      -k 'not test_order_to_cash_goods_trigger_states_and_job_position and not
      test_demo_cost_exclusion_and_cash_profile_no_double_counting and not
      test_api_command_center_and_quote_cash and not
      test_receipts_dedup_and_expected_collections_trigger and not
      test_api_overview_settings_and_bank_certification'. Legacy credential/Mongo imports
      were made lazy so selecting pure tests does not import live configuration.
