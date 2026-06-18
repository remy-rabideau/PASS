"""
Tkinter UI for sending a PlanDev schedule to ACROSS.

Flow:
  1. Pick a telescope    -> loads the plan list from PlanDev
  2. Pick a plan, fidelity, and status
  3. Click "Send to ACROSS"

The telescope selection sets across_sdk.TELESCOPE_UUID.
Fidelity and status are applied to the built ScheduleCreate before posting.

Launch with launch() from main.py.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from across.client import Client
from across.sdk.v1.models.schedule_status import ScheduleStatus
from across.sdk.v1.models.schedule_fidelity import ScheduleFidelity
from across.sdk.v1.api_client import ApiClient

import across_sdk
from across_sdk import create_schedule
from across_data import get_telescopes, get_plans, get_activity_types
from hasura_client import get_simulation
from config import ACROSS_CLIENT_ID, ACROSS_CLIENT_SECRET


class ScheduleUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PlanDev → ACROSS")
        self.root.geometry("460x550")

        # Data loaded from the APIs
        self.telescopes: list[dict] = []
        self.plans: list[dict] = []

        self._build_widgets()
        self._set_status("Loading telescopes…")
        # Defer the network call until after the window is drawn.
        self.root.after(50, self._load_telescopes)

    # -- layout -------------------------------------------------------------

    def _build_widgets(self):
        ttk.Label(self.root, text="Telescope").grid(row=0, column=0, sticky="w", padx=12, pady=6)
        self.telescope_cb = ttk.Combobox(self.root, state="disabled", width=32)
        self.telescope_cb.grid(row=0, column=1, padx=12, pady=6)
        self.telescope_cb.bind("<<ComboboxSelected>>", self._on_telescope_selected)

        ttk.Label(self.root, text="Plan").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.plan_cb = ttk.Combobox(self.root, state="disabled", width=32)
        self.plan_cb.grid(row=1, column=1, padx=12, pady=6)

        ttk.Label(self.root, text="Fidelity").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.fidelity_cb = ttk.Combobox(
            self.root, state="readonly", width=32,
            values=[e.value for e in ScheduleFidelity],
        )
        self.fidelity_cb.set(ScheduleFidelity.LOW.value)
        self.fidelity_cb.grid(row=2, column=1, padx=12, pady=6)

        ttk.Label(self.root, text="Status").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        self.status_cb = ttk.Combobox(
            self.root, state="readonly", width=32,
            values=[e.value for e in ScheduleStatus],
        )
        self.status_cb.set(ScheduleStatus.PLANNED.value)
        self.status_cb.grid(row=3, column=1, padx=12, pady=6)

        ttk.Label(self.root, text="Activity types").grid(row=4, column=0, sticky="nw", padx=12, pady=6)
        self.activity_lb = tk.Listbox(self.root, selectmode="multiple", width=32, height=6, exportselection=False)
        self.activity_lb.grid(row=4, column=1, padx=12, pady=6)

        self.send_btn = ttk.Button(
            self.root, text="Send to ACROSS", state="disabled", command=self._send
        )
        self.send_btn.grid(row=5, column=0, columnspan=2, pady=16)

        self.status_lbl = ttk.Label(self.root, text="", foreground="#555", wraplength=400)
        self.status_lbl.grid(row=6, column=0, columnspan=2, sticky="w", padx=12)

    # -- helpers ------------------------------------------------------------

    def _set_status(self, text: str, error: bool = False):
        self.status_lbl.config(text=text, foreground=("#b00" if error else "#555"))
        self.root.update_idletasks()   # show the message before any blocking call

    def _refresh_send_state(self):
        """Enable the send button only when telescope and plan are chosen."""
        ready = bool(
            getattr(across_sdk, "TELESCOPE_UUID", "")
            and self.plan_cb.get()
        )
        self.send_btn.config(state="normal" if ready else "disabled")

    # -- data loading -------------------------------------------------------

    def _load_telescopes(self):
        try:
            self.telescopes = get_telescopes()
        except Exception as e:
            self._set_status(f"Failed to load telescopes: {e}", error=True)
            return

        self.telescope_cb["values"] = [t["name"] for t in self.telescopes]
        self.telescope_cb.config(state="readonly")
        self._set_status(f"Loaded {len(self.telescopes)} telescope(s). Select one.")

    def _on_telescope_selected(self, _event=None):
        name = self.telescope_cb.get()
        telescope = next((t for t in self.telescopes if t["name"] == name), None)
        if telescope is None:
            return

        across_sdk.TELESCOPE_UUID = telescope["id"]

        self.plan_cb.set("")
        self.plan_cb.config(state="disabled")
        self._refresh_send_state()

        self._set_status("Telescope set. Loading plans…")
        self._load_plans()

    def _on_plan_selected(self, _event=None):
        self._refresh_send_state()
        plan = next((p for p in self.plans if p["name"] == self.plan_cb.get()), None)
        if plan is None:
            return

        self._set_status("Loading activity types…")
        try:
            names = get_activity_types(plan["id"])
        except Exception as e:
            self._set_status(f"Failed to load activity types: {e}", error=True)
            return

        self.activity_lb.delete(0, tk.END)
        for name in names:
            self.activity_lb.insert(tk.END, name)
        # Pre-select all by default so nothing is silently dropped.
        self.activity_lb.select_set(0, tk.END)
        self._set_status(f"Loaded {len(names)} activity type(s). Adjust selection, then send.")

    def _load_plans(self):
        try:
            self.plans = get_plans()
        except Exception as e:
            self._set_status(f"Failed to load plans: {e}", error=True)
            return

        self.plan_cb["values"] = [p["name"] for p in self.plans]
        self.plan_cb.config(state="readonly")
        self.plan_cb.bind("<<ComboboxSelected>>", self._on_plan_selected)
        self._set_status(f"Loaded {len(self.plans)} plan(s). Select one, then send.")

    # -- send ---------------------------------------------------------------

    def _send(self):
        plan = next((p for p in self.plans if p["name"] == self.plan_cb.get()), None)
        if plan is None:
            self._set_status("Pick a plan first.", error=True)
            return

        try:
            self._set_status("Fetching simulation…")
            selected = [self.activity_lb.get(i) for i in self.activity_lb.curselection()]
            across_sdk.ALLOWED_ACTIVITY_TYPES = selected
            simulation = get_simulation(plan["id"])

            self._set_status("Building schedule…")
            schedule = create_schedule(simulation, plan["id"])
            # Apply the UI selections for fidelity/status onto the built object.
            schedule.fidelity = ScheduleFidelity(self.fidelity_cb.get())
            schedule.status = ScheduleStatus(self.status_cb.get())

            print(ApiClient().sanitize_for_serialization(schedule))

            self._set_status("Posting to ACROSS…")
            client = Client(
                client_id=ACROSS_CLIENT_ID,
                client_secret=ACROSS_CLIENT_SECRET,
            )
            new_id = client.schedule.post(schedule=schedule)

            n = len(schedule.observations)
            self._set_status(f"Sent {n} observation(s). ACROSS schedule id: {new_id}")
            messagebox.showinfo("Success", f"Schedule sent.\nACROSS id: {new_id}")
        except Exception as e:
            self._set_status(f"Send failed: {e}", error=True)
            messagebox.showerror("Send failed", str(e))


def launch():
    root = tk.Tk()
    ScheduleUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch()