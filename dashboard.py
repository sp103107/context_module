"""Streamlit Dashboard - Mission Control for AoS Context Module.

Real-time monitoring and control interface for agent runs.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import pandas as pd
import requests
import streamlit as st

# Configuration
API_BASE_URL = "http://localhost:8000"
REFRESH_INTERVAL = 2  # seconds


def check_server_health() -> bool:
    """Check if the API server is online.

    Returns:
        True if server is online, False otherwise
    """
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def get_run_state(run_id: str) -> Optional[Dict[str, Any]]:
    """Fetch working set state for a run.

    Args:
        run_id: Run identifier

    Returns:
        Working set JSON or None if not found/error
    """
    try:
        response = requests.get(f"{API_BASE_URL}/runs/{run_id}", timeout=5)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            st.error(f"API Error: {response.status_code}")
            return None
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to server. Is it running?")
        return None
    except Exception as e:
        st.error(f"Error fetching state: {e}")
        return None


def create_snapshot(run_id: str) -> Optional[str]:
    """Create a resume pack snapshot.

    Args:
        run_id: Run identifier

    Returns:
        Pack path if successful, None otherwise
    """
    try:
        response = requests.post(
            f"{API_BASE_URL}/runs/{run_id}/snapshot", timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                return result.get("pack_path")
            else:
                st.error(f"Snapshot failed: {result.get('error')}")
                return None
        else:
            st.error(f"API Error: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error creating snapshot: {e}")
        return None


def get_status_color(status: str) -> str:
    """Get color code for status.

    Args:
        status: Status string

    Returns:
        Color name for Streamlit
    """
    status_colors = {
        "DONE": "green",
        "BUSY": "yellow",
        "BOOT": "blue",
        "IDLE": "gray",
        "WAITING_INPUT": "orange",
        "PAUSED": "purple",
        "FAILED": "red",
    }
    return status_colors.get(status, "gray")


def format_context_item(item: Any) -> Dict[str, Any]:
    """Format a context item for DataFrame display.

    Args:
        item: Context item (dict or string)

    Returns:
        Formatted dict with Time, Role, Content
    """
    if isinstance(item, dict):
        return {
            "Time": item.get("timestamp", "N/A"),
            "Role": item.get("role", "system"),
            "Content": str(item.get("content", ""))[:200],  # Truncate long content
            "Priority": item.get("priority", 0),
        }
    else:
        return {
            "Time": "N/A",
            "Role": "system",
            "Content": str(item)[:200],
            "Priority": 0,
        }


# Page Configuration
st.set_page_config(
    page_title="AoS Context Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar
with st.sidebar:
    st.title("🎯 Mission Control")
    st.divider()

    # Server Health Check
    st.subheader("Server Status")
    is_online = check_server_health()
    if is_online:
        st.success("🟢 Online")
    else:
        st.error("🔴 Offline")
        st.info("Make sure the server is running:\n`python server.py`")

    st.divider()

    # Run Selector
    st.subheader("Run Configuration")
    run_id = st.text_input(
        "Run ID",
        value=st.session_state.get("run_id", "run_1"),
        key="run_id_input",
    )
    st.session_state["run_id"] = run_id

    # Auto-Refresh Toggle
    auto_refresh = st.checkbox(
        "🔴 Live Poll (2s)", value=st.session_state.get("auto_refresh", False)
    )
    st.session_state["auto_refresh"] = auto_refresh

    if auto_refresh:
        st.info("Auto-refreshing every 2 seconds...")
        time.sleep(REFRESH_INTERVAL)
        st.rerun()

# Main Content
st.title("AoS Context Dashboard")
st.divider()

# Fetch Run State
run_id = st.session_state.get("run_id", "run_1")
state = get_run_state(run_id)

if state is None:
    # Waiting/Error State
    st.warning("⏳ Waiting for Agent to Boot... (Run ID not found)")
    st.info(f"Run ID: `{run_id}`")
    st.info(
        "The agent hasn't created this run yet, or the run ID is incorrect."
    )
    st.info("💡 Tip: Check the server logs or create a new run via API.")
else:
    # Header - Task ID: Objective
    task_id = state.get("task_id", "Unknown")
    objective = state.get("objective", "No objective set")
    st.markdown(f"## 📋 **{task_id}**: {objective}")

    # Metrics Row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        status = state.get("status", "UNKNOWN")
        status_color = get_status_color(status)
        st.metric("Status", status)

    with col2:
        stage = state.get("current_stage", "N/A")
        st.metric("Stage", stage)

    with col3:
        update_seq = state.get("_update_seq", 0)
        st.metric("Update Sequence", update_seq)

    with col4:
        sliding_context = state.get("sliding_context", [])
        memory_count = len(sliding_context)
        st.metric("Memory Count", memory_count)

    st.divider()

    # Action Center
    st.subheader("🎬 Action Center")

    col_action1, col_action2 = st.columns(2)

    with col_action1:
        next_action = state.get("next_action", "")
        if next_action:
            st.info(f"👉 **Next:** {next_action}")
        else:
            st.info("👉 **Next:** No action planned")

    with col_action2:
        last_action = state.get("last_action_summary", "")
        if last_action:
            st.info(f"⏮️ **Prev:** {last_action}")
        else:
            st.info("⏮️ **Prev:** No previous action")

    st.divider()

    # Deep Dive Tabs
    tab1, tab2, tab3 = st.tabs(["🧠 Working Memory", "📋 Mission Specs", "💾 Controls"])

    with tab1:
        # Pinned Context
        with st.expander("📌 Pinned (Long Term)", expanded=True):
            pinned = state.get("pinned_context", [])
            if pinned:
                for idx, item in enumerate(pinned):
                    if isinstance(item, dict):
                        content = item.get("content", str(item))
                        timestamp = item.get("timestamp", "N/A")
                        st.markdown(f"**{idx + 1}.** [{timestamp}] {content}")
                    else:
                        st.markdown(f"**{idx + 1}.** {str(item)}")
            else:
                st.info("No pinned context items")

        # Sliding Context
        with st.expander("📊 Sliding (Recent)", expanded=True):
            sliding = state.get("sliding_context", [])
            if sliding:
                # Convert to DataFrame
                df_data = [format_context_item(item) for item in sliding]
                df = pd.DataFrame(df_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No sliding context items")

    with tab2:
        # Acceptance Criteria
        st.subheader("✅ Acceptance Criteria")
        criteria = state.get("acceptance_criteria", [])
        if criteria:
            for idx, criterion in enumerate(criteria):
                st.checkbox(criterion, value=False, key=f"criteria_{idx}")
        else:
            st.info("No acceptance criteria defined")

        st.divider()

        # Constraints
        st.subheader("⚠️ Constraints")
        constraints = state.get("constraints", [])
        if constraints:
            for constraint in constraints:
                st.warning(f"⚠️ {constraint}")
        else:
            st.info("No constraints defined")

        # Additional Info
        st.divider()
        st.subheader("📊 Additional Information")

        col_info1, col_info2 = st.columns(2)

        with col_info1:
            blockers = state.get("blockers", [])
            if blockers:
                st.error("🚫 Blockers:")
                for blocker in blockers:
                    st.error(f"  - {blocker}")
            else:
                st.success("✅ No blockers")

        with col_info2:
            artifact_refs = state.get("artifact_refs", [])
            if artifact_refs:
                st.info("📎 Artifacts:")
                for artifact in artifact_refs:
                    if isinstance(artifact, dict):
                        st.info(f"  - {artifact.get('type', 'Unknown')}: {artifact.get('ref', 'N/A')}")
                    else:
                        st.info(f"  - {artifact}")
            else:
                st.info("📎 No artifacts")

    with tab3:
        st.subheader("💾 Snapshot & Control")

        # Create Snapshot Button
        if st.button("📸 Create Snapshot", type="primary", use_container_width=True):
            with st.spinner("Creating snapshot..."):
                pack_path = create_snapshot(run_id)
                if pack_path:
                    st.success(f"✅ Snapshot created successfully!")
                    st.code(pack_path, language=None)
                    st.info("💡 The snapshot file is saved on the server.")

        st.divider()

        # Run Information
        st.subheader("ℹ️ Run Information")
        info_col1, info_col2 = st.columns(2)

        with info_col1:
            st.text(f"Task ID: {state.get('task_id', 'N/A')}")
            st.text(f"Thread ID: {state.get('thread_id', 'N/A')}")
            st.text(f"Run ID: {state.get('run_id', 'N/A')}")

        with info_col2:
            st.text(f"Schema Version: {state.get('_schema_version', 'N/A')}")
            st.text(f"Update Sequence: {state.get('_update_seq', 0)}")
            st.text(f"Status: {state.get('status', 'N/A')}")

        # Raw JSON View
        with st.expander("🔍 Raw JSON (Debug)", expanded=False):
            st.json(state)

# Footer
st.divider()
st.caption(f"API Server: {API_BASE_URL} | Run ID: {run_id}")

