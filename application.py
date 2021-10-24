import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    # """Show portfolio of stocks"""

    return render_template("index.html")

@app.context_processor
def utility_processor():
    return dict(get_holdings=get_holdings, get_cash=get_cash, usd=usd, get_stocks=get_stocks, get_history=get_history)

def get_holdings():
    holdings = db.execute("SELECT stock, SUM(amount) as total_shares from purchases WHERE user_id = :id GROUP BY stock HAVING SUM(amount) > 0",
                        id=session["user_id"])

    # rows = []
    # for h in holdings:
    #     share = lookup(h["stock"])
    #     rows.append({ "symbol": h["stock"],
    #                   "name": share["name"],
    #                   "shares": h["total_shares"],
    #                   "price": share["price"],
    #                   "total": h["total_shares"] * share["price"]
    #     })
    # the function + mapping below do the same

    def holding_to_row(h):
        share = lookup(h["stock"])
        return { "symbol": h["stock"],
                      "name": share["name"],
                      "shares": h["total_shares"],
                      "price": share["price"],
                      "total": h["total_shares"] * share["price"]
        }


    # rows = list(map(holding_to_row, holdings))
    rows = [holding_to_row(h) for h in holdings]    #this is Python comprehension - does same as line above

    # total = 0
    # for row in rows:
    #     total += row["total"]
    # this does the same as the line below

    # total = sum(map(lambda x: x["total"], rows))
    total = sum([r["total"] for r in rows]) #this is Python comprehension - does same as line above
    return {
        "rows": rows,
        "total": total
    }


def get_cash():
    rows = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    return rows[0]["cash"]

def get_stocks():
    stocks = db.execute("SELECT DISTINCT stock from purchases WHERE user_id = :id AND amount != 0", id=session["user_id"])
    return stocks

def get_history():
    history = db.execute("SELECT * FROM purchases WHERE user_id = :id ORDER BY time DESC", id=session["user_id"])
    return history


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # """Buy shares of stock"""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 403)
        stock_quote = lookup(request.form.get("symbol"))
        if stock_quote == None:
            return apology("stock symbol not found", 404)
        if not request.form.get("shares"):
            return apology("must provide number of shares", 403)

        shares = int(request.form.get("shares"))
        cash = get_cash()
        purchase_price = shares * stock_quote["price"]
        if purchase_price > cash:
            return apology("short of cash", 403)
        remaining = cash-purchase_price

        db.execute("UPDATE users SET cash = :remaining WHERE id = :id", remaining=remaining, id=session["user_id"])
        db.execute("INSERT INTO purchases(user_id, stock, price, amount) VALUES (:id, :stock, :price, :amount)",
                    id=session["user_id"],
                    stock=stock_quote["symbol"],
                    price=stock_quote["price"],
                    amount=shares)

        print(f"""User id: {session["user_id"]}, Number of shares: { shares }, Cash: {cash},
        Purchase price: {purchase_price}, Remaining: {remaining}, Real-time cash: {get_cash()}""")

        flash('Bought!')
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    # """Show history of transactions"""
    return render_template("history.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    # Log user in

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    # """Get stock quote."""

    if request.method == "POST":
        stock_quote = lookup(request.form.get("symbol"))
        if stock_quote == None:
            return apology("stock symbol not found", 404)
        stock_quote["price_in_usd"] = usd(stock_quote["price"])
        return render_template("quoted.html", stock_quote=stock_quote)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 403)
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 403)

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        if len(rows) != 0:
            return apology("username already exists", 403)

        hash_val = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users(username, hash) VALUES (:username, :hash_val)",
                   username=request.form.get("username"),
                   hash_val=hash_val)

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        session["user_id"] = rows[0]["id"]
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    # """Sell shares of stock"""

    if request.method == "POST":

        if not request.form.get("shares"):
            return apology("must provide a number of shares", 403)
        shares = int(request.form.get("shares"))

        stock_quote = lookup(request.form.get("symbol"))
        if stock_quote == None:
            return apology("stock symbol not found", 404)

        stocks = db.execute("SELECT stock, SUM(amount) as total_shares from purchases WHERE user_id = :id AND stock = :stock GROUP BY stock",
                            id=session["user_id"],
                            stock=request.form.get("symbol"))
        if stocks[0]["total_shares"] < shares:
            return apology("you don't own that amount of stocks!", 403)

        purchase_price = shares * stock_quote["price"]
        updated_cash = get_cash() + purchase_price
        amount = shares * -1
        db.execute("UPDATE users SET cash = :updated WHERE id = :id", updated=updated_cash, id=session["user_id"])
        db.execute("INSERT INTO purchases(user_id, stock, price, amount) VALUES (:id, :stock, :price, :amount)",
                    id=session["user_id"],
                    stock=stock_quote["symbol"],
                    price=stock_quote["price"],
                    amount=amount)

        flash('Sold!')
        return redirect("/")

    else:
        return render_template("sell.html")

@app.route("/change_pass", methods=["GET", "POST"])
@login_required
def change_pass():
    if request.method == "POST":
        if not request.form.get("password"):
            return apology("must provide current password", 403)
        elif not request.form.get("new"):
            return apology("must provide new password", 403)

        rows = db.execute("SELECT hash FROM users WHERE id = :id",
                          id=session["user_id"])
        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("you entered current password incorrectly", 403)

        new_hash = generate_password_hash(request.form.get("new"))
        db.execute("UPDATE users SET hash = :new_hash WHERE id = :id",
                   id=session["user_id"],
                   new_hash=new_hash)

        flash('Password changed!')
        return redirect("/")

    else:
        return render_template("change_pass.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
