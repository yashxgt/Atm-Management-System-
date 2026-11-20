"""
ATM Management System - Streamlit version (single file)
Run with:   streamlit run atm_streamlit.py
Install:    pip install streamlit
Demo login: account 1001, PIN 2580
"""
import csv
import os
import random
import tempfile
from datetime import datetime, date

import streamlit as st

# ---------------- Configuration ----------------
DAILY_LIMIT = 20000                 # max total withdrawal per account per day (Rs.)
MAX_PIN_ATTEMPTS = 3                # wrong PINs allowed before the account is blocked
NOTE_MULTIPLE = 100                 # withdrawals must be a multiple of this
DENOMINATIONS = (500, 200, 100)     # notes the ATM dispenses (largest first)
DEFAULT_ATM_CASH = 100000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.csv")
TRANSACTIONS_FILE = os.path.join(BASE_DIR, "transactions.csv")
CASH_FILE = os.path.join(BASE_DIR, "atm_cash.txt")

ACCOUNT_FIELDS = ["account_no", "name", "pin", "balance", "status",
                  "daily_withdrawn", "last_withdraw_date", "failed_attempts"]
TRANSACTION_FIELDS = ["timestamp", "account_no", "type", "amount",
                      "balance_after", "status"]


# =====================================================================
#  ATM logic (no UI code here - every method returns (ok, message))
# =====================================================================
class ATM:

    def __init__(self, accounts_file=ACCOUNTS_FILE,
                 transactions_file=TRANSACTIONS_FILE, cash_file=CASH_FILE,
                 cash=None):
        self.accounts_file = accounts_file
        self.transactions_file = transactions_file
        self.cash_file = cash_file
        self._prepare_files(cash)
        self._load_accounts()
        self.cash = self._load_cash()

    # ---------------- File handling ----------------
    def _prepare_files(self, cash):
        if not os.path.exists(self.accounts_file):
            demo = {"account_no": "1001", "name": "Demo User", "pin": "2580",
                    "balance": 10000, "status": "ACTIVE", "daily_withdrawn": 0,
                    "last_withdraw_date": "", "failed_attempts": 0}
            with open(self.accounts_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=ACCOUNT_FIELDS)
                writer.writeheader()
                writer.writerow(demo)
        if not os.path.exists(self.transactions_file):
            with open(self.transactions_file, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=TRANSACTION_FIELDS).writeheader()
        if cash is not None or not os.path.exists(self.cash_file):
            self.set_cash(DEFAULT_ATM_CASH if cash is None else cash)

    def _load_accounts(self):
        self.accounts = {}
        with open(self.accounts_file, newline="") as f:
            for row in csv.DictReader(f):
                row["balance"] = int(row["balance"])
                row["daily_withdrawn"] = int(row.get("daily_withdrawn") or 0)
                row["failed_attempts"] = int(row.get("failed_attempts") or 0)
                row["last_withdraw_date"] = row.get("last_withdraw_date") or ""
                self.accounts[row["account_no"]] = row

    def _save_accounts(self):
        with open(self.accounts_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=ACCOUNT_FIELDS)
            writer.writeheader()
            writer.writerows(self.accounts.values())

    def _load_cash(self):
        with open(self.cash_file) as f:
            return int(f.read().strip())

    def set_cash(self, amount):
        self.cash = int(amount)
        with open(self.cash_file, "w") as f:
            f.write(str(self.cash))

    def _log(self, account_no, txn_type, amount, balance_after, status):
        with open(self.transactions_file, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=TRANSACTION_FIELDS).writerow({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "account_no": account_no, "type": txn_type, "amount": amount,
                "balance_after": balance_after, "status": status})

    def history(self, account_no):
        with open(self.transactions_file, newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["account_no"] == account_no]
        return list(reversed(rows))          # newest first

    # ---------------- Helpers ----------------
    @staticmethod
    def parse_amount(text):
        """Return a positive int, or None if the text is not a valid amount."""
        text = str(text).strip()
        if not text.isdigit() or int(text) <= 0:
            return None
        return int(text)

    @staticmethod
    def check_pin_rules(pin):
        """Return an error message if the PIN is not allowed, else None."""
        if not pin.isdigit():
            return "PIN can only be a number."
        if len(pin) != 4:
            return "PIN must be of 4 digits."
        if pin in ("0000", "1111", "1234", "9999"):
            return "Too easy a PIN, enter a stronger PIN."
        return None

    def withdrawn_today(self, acc):
        if acc["last_withdraw_date"] != str(date.today()):
            return 0
        return acc["daily_withdrawn"]

    def remaining_limit(self, acc_no):
        return DAILY_LIMIT - self.withdrawn_today(self.accounts[acc_no])

    @staticmethod
    def notes_for(amount):
        """Split amount into notes, largest denomination first."""
        notes = {}
        for d in DENOMINATIONS:
            count, amount = divmod(amount, d)
            if count:
                notes[d] = count
        return notes

    @staticmethod
    def generate_otp():
        return random.randint(1111, 9999)

    # ---------------- Features ----------------
    def login(self, acc_no, pin):
        acc = self.accounts.get(acc_no.strip())
        if acc is None:
            return False, "Account not found."
        if acc["status"] == "BLOCKED":
            return False, "Your account is BLOCKED. Please contact the bank."
        if pin == acc["pin"]:
            acc["failed_attempts"] = 0
            self._save_accounts()
            return True, f"Login successful. Welcome, {acc['name']}."

        acc["failed_attempts"] += 1
        if acc["failed_attempts"] >= MAX_PIN_ATTEMPTS:
            acc["status"] = "BLOCKED"
            self._save_accounts()
            self._log(acc["account_no"], "LOGIN", 0, acc["balance"], "BLOCKED")
            return False, "Account blocked after 3 wrong PINs."
        self._save_accounts()
        left = MAX_PIN_ATTEMPTS - acc["failed_attempts"]
        return False, f"Wrong PIN. {left} attempt(s) left."

    def create_account(self, name, pin, balance_text):
        error = self.check_pin_rules(pin)
        if error:
            return False, error
        balance_text = str(balance_text).strip()
        if not balance_text.isdigit():
            return False, "Invalid input. Opening balance must be a number."
        balance = int(balance_text)
        acc_no = str(max([int(a) for a in self.accounts] + [1000]) + 1)
        self.accounts[acc_no] = {
            "account_no": acc_no, "name": name.strip() or "Customer",
            "pin": pin, "balance": balance, "status": "ACTIVE",
            "daily_withdrawn": 0, "last_withdraw_date": "", "failed_attempts": 0}
        self._save_accounts()
        self._log(acc_no, "CREATE", balance, balance, "SUCCESS")
        return True, f"Account created successfully. Your account number is {acc_no}."

    def change_pin(self, acc_no, old_pin, new_pin):
        acc = self.accounts[acc_no]
        if old_pin != acc["pin"]:
            return False, "Enter correct old pin."
        error = self.check_pin_rules(new_pin)
        if error:
            return False, error
        acc["pin"] = new_pin
        self._save_accounts()
        return True, "PIN changed successfully."

    def withdraw(self, acc_no, amount_text):
        acc = self.accounts[acc_no]
        amount = self.parse_amount(amount_text)
        if amount is None:                                  # Test 4
            return False, "Invalid input. Please enter a positive number."

        def reject(message, status):
            self._log(acc_no, "WITHDRAW", amount, acc["balance"], status)
            return False, message

        if amount % NOTE_MULTIPLE != 0:                     # Test 3
            return reject(f"Amount must be a multiple of Rs. {NOTE_MULTIPLE}.",
                          "REJECTED_MULTIPLE")
        if amount > acc["balance"]:
            return reject("Insufficient balance in your account.",
                          "REJECTED_BALANCE")
        if self.withdrawn_today(acc) + amount > DAILY_LIMIT:    # Test 2
            return reject(f"Daily limit of Rs. {DAILY_LIMIT} exceeded.",
                          "REJECTED_DAILY_LIMIT")
        if amount > self.cash:                              # Test 6
            return reject("ATM has insufficient cash.", "REJECTED_ATM_CASH")

        # all checks passed -> dispense (Test 1)
        acc["balance"] -= amount
        acc["daily_withdrawn"] = self.withdrawn_today(acc) + amount
        acc["last_withdraw_date"] = str(date.today())
        self._save_accounts()
        self.set_cash(self.cash - amount)
        self._log(acc_no, "WITHDRAW", amount, acc["balance"], "SUCCESS")
        notes = " + ".join(f"{n} x Rs.{d}" for d, n in self.notes_for(amount).items())
        return True, (f"Dispensed {notes}. Balance is now Rs. {acc['balance']}. "
                      f"Transaction logged in transactions.csv.")

    def deposit(self, acc_no, amount_text):
        acc = self.accounts[acc_no]
        amount = self.parse_amount(amount_text)
        if amount is None:
            return False, "Invalid input. Please enter a positive number."
        acc["balance"] += amount
        self._save_accounts()
        self.set_cash(self.cash + amount)
        self._log(acc_no, "DEPOSIT", amount, acc["balance"], "SUCCESS")
        return True, f"Deposited Rs. {amount}. Your balance is now Rs. {acc['balance']}."


# =====================================================================
#  Test cases (the Testing table of the report)
# =====================================================================
def _make_atm(balance, cash, tmp):
    acc_file = os.path.join(tmp, "accounts.csv")
    with open(acc_file, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ACCOUNT_FIELDS)
        w.writeheader()
        w.writerow({"account_no": "1001", "name": "Demo", "pin": "2580",
                    "balance": balance, "status": "ACTIVE", "daily_withdrawn": 0,
                    "last_withdraw_date": "", "failed_attempts": 0})
    return ATM(accounts_file=acc_file,
               transactions_file=os.path.join(tmp, "transactions.csv"),
               cash_file=os.path.join(tmp, "atm_cash.txt"), cash=cash)


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run_tests():
    """Run the 6 test cases in a temporary folder. Returns a list of row dicts."""
    rows = []

    def add(name, inp, expected, actual, passed):
        rows.append({"Test": name, "Input": inp, "Expected Output": expected,
                     "Actual Output": actual, "Result": "Pass" if passed else "FAIL"})

    with tempfile.TemporaryDirectory() as t:                       # 1 Normal
        a = _make_atm(10000, 100000, t)
        ok, msg = a.withdraw("1001", "2500")
        log = _read_csv(a.transactions_file)[-1]
        add("1 (Normal)", "Withdraw Rs. 2,500 (balance Rs. 10,000, ATM has enough cash)",
            "Dispenses 5 x Rs. 500. Balance becomes Rs. 7,500. Transaction is logged.",
            msg, ok and "5 x Rs.500" in msg and a.accounts["1001"]["balance"] == 7500
            and log["status"] == "SUCCESS" and log["amount"] == "2500")

    with tempfile.TemporaryDirectory() as t:                       # 2 Boundary
        a = _make_atm(50000, 100000, t)
        ok1, m1 = a.withdraw("1001", "20000")
        ok2, m2 = a.withdraw("1001", "500")
        add("2 (Boundary)", "Withdraw exactly the daily limit of Rs. 20,000 (balance Rs. 50,000)",
            "Withdrawal allowed. A further withdrawal on the same day is rejected.",
            f"Rs. 20,000 withdrawn (40 x Rs.500). A further Rs. 500 was rejected: {m2}",
            ok1 and "40 x Rs.500" in m1 and not ok2 and "Daily limit" in m2)

    with tempfile.TemporaryDirectory() as t:                       # 3 Invalid
        a = _make_atm(10000, 100000, t)
        ok, msg = a.withdraw("1001", "250")
        add("3 (Invalid)", "Withdraw Rs. 250",
            "Message: amount must be a multiple of Rs. 100. Balance unchanged.",
            f"{msg} Balance stayed Rs. {a.accounts['1001']['balance']}.",
            not ok and "multiple of Rs. 100" in msg and a.accounts["1001"]["balance"] == 10000)

    with tempfile.TemporaryDirectory() as t:                       # 4 Invalid
        a = _make_atm(10000, 100000, t)
        ok, msg = a.withdraw("1001", "abc")
        add("4 (Invalid)", "Enter letters (abc) as the amount",
            "Message: invalid input. Menu is shown again without any crash.",
            f"{msg} No crash.",
            not ok and "Invalid input" in msg and a.accounts["1001"]["balance"] == 10000)

    with tempfile.TemporaryDirectory() as t:                       # 5 Special
        a = _make_atm(10000, 100000, t)
        results = [a.login("1001", p) for p in ("1", "2", "3")]
        saved = _read_csv(a.accounts_file)[0]["status"]
        add("5 (Special)", "Enter a wrong PIN 3 times",
            "Account is blocked and status is saved as BLOCKED in accounts.csv.",
            f"{results[-1][1]} accounts.csv now shows status {saved}.",
            not results[-1][0] and saved == "BLOCKED")

    with tempfile.TemporaryDirectory() as t:                       # 6 Special
        a = _make_atm(10000, 2000, t)
        ok, msg = a.withdraw("1001", "5000")
        add("6 (Special)", "Withdraw Rs. 5,000 when ATM has only Rs. 2,000",
            "Message: ATM has insufficient cash. No amount is deducted.",
            f"{msg} Balance stayed Rs. {a.accounts['1001']['balance']}.",
            not ok and "ATM has insufficient cash" in msg
            and a.accounts["1001"]["balance"] == 10000)
    return rows


# =====================================================================
#  Streamlit user interface
# =====================================================================
def show_login(atm):
    st.subheader("Login")
    with st.form("login_form"):
        acc_no = st.text_input("Account number")
        pin = st.text_input("PIN", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        ok, msg = atm.login(acc_no, pin)
        if ok:
            st.session_state.acc_no = acc_no.strip()
            st.rerun()
        else:
            st.error(msg)
    st.caption("Demo account: 1001 / PIN 2580")


def show_create_account(atm):
    st.subheader("Create account / PIN")
    if st.button("Send OTP"):
        st.session_state.otp = atm.generate_otp()
    if "otp" in st.session_state:
        st.info(f"Your OTP is: {st.session_state.otp}  (simulated SMS)")
        with st.form("create_form"):
            otp = st.text_input("Enter OTP")
            name = st.text_input("Your name")
            pin = st.text_input("Choose a 4-digit PIN", type="password")
            balance = st.text_input("Opening balance (Rs.)")
            submitted = st.form_submit_button("Create account")
        if submitted:
            if not otp.strip().isdigit() or int(otp) != st.session_state.otp:
                st.error("Invalid otp")
            else:
                ok, msg = atm.create_account(name, pin, balance)
                if ok:
                    del st.session_state["otp"]
                    st.success(msg)
                else:
                    st.error(msg)


def show_balance(atm, acc_no):
    st.subheader("Check balance")
    st.metric("Available balance", f"Rs. {atm.accounts[acc_no]['balance']:,}")


def show_withdraw(atm, acc_no):
    st.subheader("Withdraw amount")
    st.write(f"Balance: **Rs. {atm.accounts[acc_no]['balance']:,}**  |  "
             f"Daily limit left today: **Rs. {atm.remaining_limit(acc_no):,}**")
    with st.form("withdraw_form", clear_on_submit=True):
        amount = st.text_input("Enter the amount to withdraw (multiple of Rs. 100)")
        submitted = st.form_submit_button("Withdraw")
    if submitted:
        ok, msg = atm.withdraw(acc_no, amount)
        (st.success if ok else st.error)(msg)


def show_deposit(atm, acc_no):
    st.subheader("Deposit amount")
    with st.form("deposit_form", clear_on_submit=True):
        amount = st.text_input("Enter the amount to deposit")
        submitted = st.form_submit_button("Deposit")
    if submitted:
        ok, msg = atm.deposit(acc_no, amount)
        (st.success if ok else st.error)(msg)


def show_change_pin(atm, acc_no):
    st.subheader("Change PIN")
    with st.form("pin_form", clear_on_submit=True):
        old = st.text_input("Old PIN", type="password")
        new = st.text_input("New PIN", type="password")
        submitted = st.form_submit_button("Change PIN")
    if submitted:
        ok, msg = atm.change_pin(acc_no, old, new)
        (st.success if ok else st.error)(msg)


def show_history(atm, acc_no):
    st.subheader("Transaction history")
    rows = atm.history(acc_no)
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.write("No transactions yet.")


def show_tests():
    st.subheader("Test cases")
    if st.button("Run all tests"):
        rows = run_tests()
        st.dataframe(rows, use_container_width=True)
        if all(r["Result"] == "Pass" for r in rows):
            st.success("All 6 tests passed.")
        else:
            st.error("Some tests failed.")


def main():
    st.set_page_config(page_title="ATM Management System", page_icon="🏧")
    st.title("🏧 ATM Management System")
    atm = ATM()                       # reloads accounts / cash from the CSV files
    acc_no = st.session_state.get("acc_no")

    # ---- sidebar: ATM cash (admin) ----
    st.sidebar.metric("Cash in ATM", f"Rs. {atm.cash:,}")
    with st.sidebar.expander("Admin: set ATM cash"):
        new_cash = st.number_input("ATM cash (Rs.)", min_value=0, step=1000,
                                   value=atm.cash)
        if st.button("Update cash"):
            atm.set_cash(new_cash)
            st.rerun()

    # ---- not logged in ----
    if acc_no is None or acc_no not in atm.accounts:
        tab_login, tab_create, tab_tests = st.tabs(
            ["Login", "Create account", "Test cases"])
        with tab_login:
            show_login(atm)
        with tab_create:
            show_create_account(atm)
        with tab_tests:
            show_tests()
        return

    # ---- logged in ----
    st.sidebar.success(f"{atm.accounts[acc_no]['name']}  (A/c {acc_no})")
    page = st.sidebar.radio("Menu", ["Check balance", "Withdraw", "Deposit",
                                     "Change PIN", "Transaction history",
                                     "Test cases"])
    if st.sidebar.button("Exit / Logout"):
        st.session_state.acc_no = None
        st.rerun()

    if page == "Check balance":
        show_balance(atm, acc_no)
    elif page == "Withdraw":
        show_withdraw(atm, acc_no)
    elif page == "Deposit":
        show_deposit(atm, acc_no)
    elif page == "Change PIN":
        show_change_pin(atm, acc_no)
    elif page == "Transaction history":
        show_history(atm, acc_no)
    else:
        show_tests()


if __name__ == "__main__":
    main()
