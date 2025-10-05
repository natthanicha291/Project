import os
import struct
import sys
from datetime import datetime, timedelta
from typing import Tuple, Optional

# ----- CONFIG -----
BOOKS_FILE = "books.dat"
MEMBERS_FILE = "members.dat"
LOANS_FILE = "loans.dat"
REPORT_FILE = "report.txt"

# header: num_records (int32), free_head (int32)
HEADER_STRUCT = struct.Struct("<ii")

# Book record:
# Book_ID: 4s, Title:60s, Category:20s, Author:30s, Publisher:30s, Year:4s,
# Copies:uint32, Status:uint8, next_free:int32
BOOK_STRUCT = struct.Struct("<4s60s20s30s30s4sIBi")

# Member record:
# Member_ID:4s, Name:50s, Birth:10s, Max_loan:uint32, Status:uint8, next_free:int32
MEM_STRUCT = struct.Struct("<4s50s10sIBi")

# Loan record:
# Loan_ID:4s, Operation_type:uint8, Member_ID:4s, Book_ID:4s,
# Loan_Date:10s, Due_Date:10s, Return_Date:10s, Status:uint8, next_free:int32
LOAN_STRUCT = struct.Struct("<4sB4s4s10s10s10sBi")

# default fixed Max loan per member
DEFAULT_MAX_LOAN = 5

# Helpers for bytes/strings
def fit_str(s: str, length: int) -> bytes:
    b = s.encode("utf-8")[:length]
    if len(b) < length:
        b = b + b" " * (length - len(b))
    return b

def bytes_to_str(b: bytes) -> str:
    return b.decode("utf-8", errors="ignore").rstrip(" ").rstrip("\x00")

# File initialization
def ensure_file(path: str, record_struct: struct.Struct):
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(HEADER_STRUCT.pack(0, -1))
            f.flush()
            os.fsync(f.fileno())

# Header operations
def read_header(f) -> Tuple[int, int]:
    f.seek(0)
    data = f.read(HEADER_STRUCT.size)
    if len(data) < HEADER_STRUCT.size:
        return 0, -1
    num, free_head = HEADER_STRUCT.unpack(data)
    return num, free_head

def write_header(f, num: int, free_head: int):
    f.seek(0)
    f.write(HEADER_STRUCT.pack(num, free_head))
    f.flush()
    os.fsync(f.fileno())

def record_offset(index: int, record_struct: struct.Struct) -> int:
    return HEADER_STRUCT.size + index * record_struct.size

def read_record(f, index: int, record_struct: struct.Struct) -> Tuple:
    off = record_offset(index, record_struct)
    f.seek(off)
    data = f.read(record_struct.size)
    if len(data) < record_struct.size:
        raise IndexError("Record not found (out of range).")
    return record_struct.unpack(data)

def write_record_at(f, index: int, packed: bytes, record_struct: struct.Struct):
    off = record_offset(index, record_struct)
    f.seek(off)
    f.write(packed)
    f.flush()
    os.fsync(f.fileno())

def append_or_reuse(f, packed: bytes, record_struct: struct.Struct) -> int:
    num, free_head = read_header(f)
    if free_head != -1:
        free_idx = free_head
        rec = read_record(f, free_idx, record_struct)
        next_free = rec[-1]  # last field is next_free (int)
        write_record_at(f, free_idx, packed, record_struct)
        write_header(f, num, next_free)
        return free_idx
    else:
        idx = num
        off = record_offset(idx, record_struct)
        f.seek(off)
        f.write(packed)
        num += 1
        write_header(f, num, free_head)
        f.flush()
        os.fsync(f.fileno())
        return idx

# ID generation helpers
def fmt_id(prefix: str, n: int) -> str:
    return f"{prefix}{n:03d}"

def next_id_for_file(path: str, id_prefix: str, id_field_index: int, record_struct: struct.Struct) -> str:
    ensure_file(path, record_struct)
    with open(path, "rb") as f:
        num, free_head = read_header(f)
        if free_head != -1:
            return fmt_id(id_prefix, free_head + 1)
        n = num + 1
        return fmt_id(id_prefix, n)

def next_loan_id() -> str:
    ensure_file(LOANS_FILE, LOAN_STRUCT)
    with open(LOANS_FILE, "rb") as f:
        num, free_head = read_header(f)
        if free_head != -1:
            return fmt_id("L", free_head + 1)
        return fmt_id("L", num + 1)

def pack_book(book_id: str, title: str, category: str, author: str, publisher: str, year: str, copies: int, status: int, next_free: int) -> bytes:
    return BOOK_STRUCT.pack(
        fit_str(book_id, 4),
        fit_str(title, 60),
        fit_str(category, 20),
        fit_str(author, 30),
        fit_str(publisher, 30),
        fit_str(year, 4),
        copies,
        status,
        next_free
    )

def unpack_book(rec_tuple) -> dict:
    book_id = bytes_to_str(rec_tuple[0])
    title = bytes_to_str(rec_tuple[1])
    category = bytes_to_str(rec_tuple[2])
    author = bytes_to_str(rec_tuple[3])
    publisher = bytes_to_str(rec_tuple[4])
    year = bytes_to_str(rec_tuple[5])
    copies = rec_tuple[6]
    status = rec_tuple[7]
    next_free = rec_tuple[8]
    return {
        "Book_ID": book_id,
        "Book_Title": title,
        "Book_Category": category,
        "Author_Name": author,
        "Publisher_Name": publisher,
        "Book_year": year,
        "Book_copies": copies,
        "Book_status": status,
        "next_free": next_free
    }

def pack_member(member_id: str, name: str, birth: str, max_loan: int, status: int, next_free: int) -> bytes:
    return MEM_STRUCT.pack(
        fit_str(member_id, 4),
        fit_str(name, 50),
        fit_str(birth, 10),
        max_loan,
        status,
        next_free
    )

def unpack_member(rec_tuple) -> dict:
    member_id = bytes_to_str(rec_tuple[0])
    name = bytes_to_str(rec_tuple[1])
    birth = bytes_to_str(rec_tuple[2])
    max_loan = rec_tuple[3]
    status = rec_tuple[4]
    next_free = rec_tuple[5]
    return {
        "Member_ID": member_id,
        "Member_Name": name,
        "Member_Birth": birth,
        "Max_loan": max_loan,
        "Member_status": status,
        "next_free": next_free
    }

def pack_loan(loan_id: str, op_type: int, member_id: str, book_id: str, loan_date: str, due_date: str, return_date: str, status: int, next_free: int) -> bytes:
    return LOAN_STRUCT.pack(
        fit_str(loan_id, 4),
        op_type,
        fit_str(member_id, 4),
        fit_str(book_id, 4),
        fit_str(loan_date, 10),
        fit_str(due_date, 10),
        fit_str(return_date, 10),
        status,
        next_free
    )

def unpack_loan(rec_tuple) -> dict:
    loan_id = bytes_to_str(rec_tuple[0])
    op_type = rec_tuple[1]
    member_id = bytes_to_str(rec_tuple[2])
    book_id = bytes_to_str(rec_tuple[3])
    loan_date = bytes_to_str(rec_tuple[4])
    due_date = bytes_to_str(rec_tuple[5])
    return_date = bytes_to_str(rec_tuple[6])
    status = rec_tuple[7]
    next_free = rec_tuple[8]
    return {
        "Loan_ID": loan_id,
        "Operation_type": op_type,
        "Member_ID": member_id,
        "Book_ID": book_id,
        "Loan_Date": loan_date,
        "Due_Date": due_date,
        "Return_Date": return_date,
        "Loan_Status": status,
        "next_free": next_free
    }
#High-level record operations
def list_all_records(file_path: str, rec_struct: struct.Struct, unpack_fn):
    ensure_file(file_path, rec_struct)
    with open(file_path, "rb") as f:
        num, _ = read_header(f)
        results = []
        for i in range(num):
            try:
                tup = read_record(f, i, rec_struct)
            except IndexError:
                continue
            rec = unpack_fn(tup)
            rec["_index"] = i
            results.append(rec)
        return results

def find_record_by_id(file_path: str, rec_struct: struct.Struct, unpack_fn, id_field_name: str, target_id: str) -> Optional[Tuple[int, dict]]:
    ensure_file(file_path, rec_struct)
    with open(file_path, "rb") as f:
        num, _ = read_header(f)
        for i in range(num):
            tup = read_record(f, i, rec_struct)
            rec = unpack_fn(tup)
            if rec[id_field_name] == target_id:
                return i, rec
    return None
def get_next_book_id():
    books = list_all_records(BOOKS_FILE, BOOK_STRUCT, unpack_book)
    max_id = 0
    for b in books:
        try:
            n = int(b["Book_ID"][1:])
            if n > max_id:
                max_id = n
        except:
            continue
    return fmt_id("B", max_id + 1)
# Book operations
def add_book():
    ensure_file(BOOKS_FILE, BOOK_STRUCT)
    with open(BOOKS_FILE, "r+b") as f:
        num, free_head = read_header(f)

        book_id = get_next_book_id()

        title = input("Enter Book Title: ").strip()
        category = input("Enter Book Category: ").strip()
        author = input("Enter Author Name: ").strip()
        publisher = input("Enter Publisher Name: ").strip()
        year = input("Enter Publish Year: ").strip()[:4]
        try:
            copies = int(input("Enter Number of Copies: ").strip())
        except ValueError:
            print("Invalid copies number. Cancel.")
            return
        
        packed = pack_book(book_id, title, category, author, publisher, year, copies, 1, -1)
        idx = append_or_reuse(f, packed, BOOK_STRUCT)

        if free_head == -1:
            write_header(f, num + 1, -1)
            
        print(f"Book added. ID = {book_id} (slot {idx})")

def view_books():
    recs = list_all_records(BOOKS_FILE, BOOK_STRUCT, unpack_book)
    print("\n--- Books ---")
    print("ID   | Title                          | Category      | Author         | Copies | Status")
    print("-"*100)
    for r in recs:
        status = "Active" if r["Book_status"] == 1 else "Deleted"
        print(f"{r['Book_ID']:<4} | {r['Book_Title'][:30]:<30} | {r['Book_Category'][:12]:<12} | {r['Author_Name'][:14]:<14} | {r['Book_copies']:<6} | {status}")
    print()

def update_book():
    bid = input("Enter Book ID to update: ").strip()
    res = find_record_by_id(BOOKS_FILE, BOOK_STRUCT, unpack_book, "Book_ID", bid)
    if not res:
        print("Book not found.")
        return
    idx, rec = res
    if rec["Book_status"] != 1:
        print("Book is deleted/inactive.")
        return

    print("Leave blank to keep current.")

    BookID = input(f"Book ID [{rec['Book_ID']}]: ").strip() or rec['Book_ID']
    title = input(f"Title [{rec['Book_Title']}]: ").strip() or rec['Book_Title']
    category = input(f"Category [{rec['Book_Category']}]: ").strip() or rec['Book_Category']
    author = input(f"Author [{rec['Author_Name']}]: ").strip() or rec['Author_Name']
    publisher = input(f"Publisher [{rec['Publisher_Name']}]: ").strip() or rec['Publisher_Name']
    year = input(f"Year [{rec['Book_year']}]: ").strip() or rec['Book_year']
    copies_str = input(f"Copies [{rec['Book_copies']}]: ").strip()

    try:
        copies = int(copies_str) if copies_str else rec['Book_copies']
    except ValueError:
        print("Invalid copies. Aborted.")
        return
    
    packed = pack_book(rec['Book_ID'], title, category, author, publisher, year, copies, 1, rec['next_free'])
    with open(BOOKS_FILE, "r+b") as f:
        write_record_at(f, idx, packed, BOOK_STRUCT)
    print("Book updated.")

def delete_book():
    bid = input("Enter Book ID to delete: ").strip()
    res = find_record_by_id(BOOKS_FILE, BOOK_STRUCT, unpack_book, "Book_ID", bid)
    if not res:
        print("Book not found.")
        return
    idx, rec = res
    if rec["Book_status"] == 0:
        print("Book already deleted.")
        return
    
    with open(BOOKS_FILE, "r+b") as f:
        num, free_head = read_header(f)
        packed = pack_book(rec['Book_ID'], rec['Book_Title'], rec['Book_Category'], rec['Author_Name'], rec['Publisher_Name'], rec['Book_year'], rec['Book_copies'], 0, free_head)
        
        write_record_at(f, idx, packed, BOOK_STRUCT)
        write_header(f, num, idx)
    print("Book deleted (slot freed).")

#  Member operations
def get_next_member_id():
    # อ่านสมาชิกทั้งหมด (active + deleted)
    members = list_all_records(MEMBERS_FILE, MEM_STRUCT, unpack_member)
    max_id = 0
    for m in members:
        try:
            n = int(m["Member_ID"][1:])  # ตัดตัว M แล้วแปลงเป็นเลข
            if n > max_id:
                max_id = n
        except ValueError:
            continue
    # คืนค่า Member_ID ใหม่
    return fmt_id("M", max_id + 1)

def add_member():
    ensure_file(MEMBERS_FILE, MEM_STRUCT)
    with open(MEMBERS_FILE, "r+b") as f:
        num, free_head = read_header(f)

        member_id = get_next_member_id()  # ใช้ ID ใหม่

        name = input("Enter Member Name: ").strip()
        birth = input("Enter Birth Date (YYYY-MM-DD): ").strip()[:10]
        max_loan = DEFAULT_MAX_LOAN

        packed = pack_member(member_id, name, birth, max_loan, 1, -1)
        idx = append_or_reuse(f, packed, MEM_STRUCT)  

        if free_head == -1:
            write_header(f, num + 1, -1)  # อัพเดตจำนวนสมาชิก

        print(f"Member added. ID = {member_id} (slot {idx}). Max loan = {max_loan}")


def view_members():
    recs = list_all_records(MEMBERS_FILE, MEM_STRUCT, unpack_member)
    print("\n--- Members ---")
    print("ID   | Name                          | Birth      | MaxLoan | Status")
    print("-"*80)
    for r in recs:
        status = "Active" if r["Member_status"] == 1 else "Deleted"
        print(f"{r['Member_ID']:<4} | {r['Member_Name'][:30]:<30} | {r['Member_Birth']:<10} | {r['Max_loan']:<7} | {status}")
    print()

def update_member():
    mid = input("Enter Member ID to update: ").strip()
    res = find_record_by_id(MEMBERS_FILE, MEM_STRUCT, unpack_member, "Member_ID", mid)
    if not res:
        print("Member not found.")
        return
    idx, rec = res
    if rec["Member_status"] != 1:
        print("Member deleted/inactive.")
        return

    print("Leave blank to keep current.")
    name = input(f"Name [{rec['Member_Name']}]: ").strip() or rec['Member_Name']
    birth = input(f"Birth [{rec['Member_Birth']}]: ").strip() or rec['Member_Birth']

    packed = pack_member(rec['Member_ID'], name, birth, rec['Max_loan'], 1, rec['next_free'])
    with open(MEMBERS_FILE, "r+b") as f:
        write_record_at(f, idx, packed, MEM_STRUCT)
    print("Member updated.")

def delete_member():
    mid = input("Enter Member ID to delete: ").strip()
    res = find_record_by_id(MEMBERS_FILE, MEM_STRUCT, unpack_member, "Member_ID", mid)
    if not res:
        print("Member not found.")
        return
    idx, rec = res
    if rec["Member_status"] == 0:
        print("Member already deleted.")
        return
    
    with open(MEMBERS_FILE, "r+b") as f:
        num, free_head = read_header(f)
        packed = pack_member(rec['Member_ID'], rec['Member_Name'], rec['Member_Birth'], rec['Max_loan'], 0, free_head)
        write_record_at(f, idx, packed, MEM_STRUCT)
        write_header(f, num, idx)
    print("Member deleted (slot freed).")

# Loan operations (borrow/return)
def borrow_book():
    member_id = input("Enter Member ID: ").strip()
    res_m = find_record_by_id(MEMBERS_FILE, MEM_STRUCT, unpack_member, "Member_ID", member_id)
    if not res_m:
        print("Member not found or inactive.")
        return
    m_idx, member = res_m
    if member["Member_status"] != 1:
        print("Member inactive.")
        return

    loans = list_all_records(LOANS_FILE, LOAN_STRUCT, unpack_loan)
    current_borrowed = sum(1 for l in loans if l["Member_ID"] == member_id and l["Loan_Status"] == 1)

    book_ids = input("Enter Book IDs to borrow (comma separated): ").strip().split(",")

    for book_id in [b.strip() for b in book_ids if b.strip()]:
        if current_borrowed >= member["Max_loan"]:
            print(f"Member reached max loan limit ({member['Max_loan']}). Cannot borrow {book_id}.")
            continue

        res_b = find_record_by_id(BOOKS_FILE, BOOK_STRUCT, unpack_book, "Book_ID", book_id)
        if not res_b:
            print(f"Book {book_id} not found.")
            continue
        b_idx, book = res_b
        if book["Book_status"] != 1:
            print(f"Book {book_id} inactive.")
            continue
        if book["Book_copies"] <= 0:
            print(f"No available copies for {book_id}.")
            continue

        book["Book_copies"] -= 1
        with open(BOOKS_FILE, "r+b") as bf:
            packed_book = pack_book(book["Book_ID"], book["Book_Title"], book["Book_Category"],
                                    book["Author_Name"], book["Publisher_Name"], book["Book_year"],
                                    book["Book_copies"], 1, book["next_free"])
            write_record_at(bf, b_idx, packed_book, BOOK_STRUCT)

        ensure_file(LOANS_FILE, LOAN_STRUCT)
        with open(LOANS_FILE, "r+b") as lf:
            loan_id = next_loan_id()
            loan_date = datetime.now().strftime("%Y-%m-%d")
            due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            packed_loan = pack_loan(loan_id, 1, member_id, book_id, loan_date, due_date, "-", 1, -1)
            loan_idx = append_or_reuse(lf, packed_loan, LOAN_STRUCT)
            print(f"Borrow successful. Loan ID = {loan_id} (slot {loan_idx}). Due date: {due_date}")

        current_borrowed += 1

def return_book():
    loan_ids = input("Enter Loan IDs to return (comma separated): ").strip().split(",")
    loan_ids = [lid.strip() for lid in loan_ids if lid.strip()]

    for loan_id in loan_ids:
        res = find_record_by_id(LOANS_FILE, LOAN_STRUCT, unpack_loan, "Loan_ID", loan_id)
        if not res:
            print(f"Loan {loan_id} not found.")
            continue

        l_idx, loan = res
        if loan["Loan_Status"] == 0:
            print(f"Loan {loan_id} already returned.")
            continue

        return_date = datetime.now().strftime("%Y-%m-%d")
        packed_return = pack_loan(
            loan["Loan_ID"], 
            2,  # Operation_type = 2 = return
            loan["Member_ID"], 
            loan["Book_ID"], 
            loan["Loan_Date"], 
            loan["Due_Date"], 
            return_date, 
            0,  # Loan_Status = 0 = returned
            -1
        )
        with open(LOANS_FILE, "r+b") as lf:
            write_record_at(lf, l_idx, packed_return, LOAN_STRUCT)
        res_b = find_record_by_id(BOOKS_FILE, BOOK_STRUCT, unpack_book, "Book_ID", loan["Book_ID"])
        if res_b:
            b_idx, book = res_b
            book["Book_copies"] += 1
            with open(BOOKS_FILE, "r+b") as bf:
                packed_book = pack_book(
                    book["Book_ID"], book["Book_Title"], book["Book_Category"],
                    book["Author_Name"], book["Publisher_Name"], book["Book_year"],
                    book["Book_copies"], 1, book["next_free"]
                )
                write_record_at(bf, b_idx, packed_book, BOOK_STRUCT)

        print(f"Book {loan['Book_ID']} returned successfully. Loan {loan_id} closed.")


def view_loans():
    recs = list_all_records(LOANS_FILE, LOAN_STRUCT, unpack_loan)
    print("\n--- Loans ---")
    print("LoanID | MemID | BookID | LoanDate   | DueDate    | ReturnDate | Status")
    print("-"*90)
    for r in recs:
        status = "Borrowed" if r["Loan_Status"] == 1 else "Returned"
        print(f"{r['Loan_ID']:<6} | {r['Member_ID']:<5} | {r['Book_ID']:<5} | {r['Loan_Date']:<10} | {r['Due_Date']:<10} | {r['Return_Date']:<10} | {status}")
    print()

# Report generation
def generate_report():
    ensure_file(BOOKS_FILE, BOOK_STRUCT)
    ensure_file(MEMBERS_FILE, MEM_STRUCT)
    ensure_file(LOANS_FILE, LOAN_STRUCT)

    books = list_all_records(BOOKS_FILE, BOOK_STRUCT, unpack_book)
    members = list_all_records(MEMBERS_FILE, MEM_STRUCT, unpack_member)
    loans = list_all_records(LOANS_FILE, LOAN_STRUCT, unpack_loan)

    active_books = [b for b in books if b["Book_status"] == 1]
    deleted_books = [b for b in books if b["Book_status"] == 0]
    borrowed_now = sum(1 for l in loans if l["Loan_Status"] == 1)
    available_now = sum(b["Book_copies"] for b in active_books)

    grouped = {}
    for l in loans:
        key = (l["Member_ID"], l["Loan_Date"], l["Due_Date"], l["Return_Date"], l["Loan_Status"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(l["Book_ID"])

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("Library Borrow System - Summary Report")
    lines.append(f"Generated At : {now} (+07:00)")
    lines.append("App Version  : 1.0")
    lines.append("Encoding     : UTF-8")
    lines.append("")

    headers = ["MemberID", "MemberName", "BookID", "Titles", "LoanDate", "DueDate", "ReturnDate", "Status"]
    rows = []
    for (mid, loan_date, due_date, return_date, status), book_ids in grouped.items():
        member_name = next((m["Member_Name"] for m in members if m["Member_ID"] == mid), "-")
        titles = [next((b["Book_Title"] for b in books if b["Book_ID"] == bid), "-") for bid in book_ids]
        status_str = "Borrowed" if status == 1 else "Returned"
        rows.append([
            mid,
            member_name,
            ",".join(book_ids),
            ",".join(titles),
            loan_date,
            due_date,
            return_date,
            status_str
        ])

    all_rows = [headers] + rows
    col_widths = [max(len(str(row[i])) for row in all_rows) for i in range(len(headers))]

    header_line = " | ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers)))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    lines.append(header_line)
    lines.append(sep_line)

    for row in rows:
        line = " | ".join(f"{str(row[i]):<{col_widths[i]}}" for i in range(len(row)))
        lines.append(line)

    lines.append("")
    lines.append("Summary (Active Books Only)")
    lines.append(f"- Total Books : {len(books)}")
    lines.append(f"- Active Books : {len(active_books)}")
    lines.append(f"- Deleted Books : {len(deleted_books)}")
    lines.append(f"- Borrowed Now : {borrowed_now}")
    lines.append(f"- Available Now : {available_now}")
    lines.append("")
    lines.append("Borrow Statistics (Active only)")

    # borrow counts
    borrow_count = {}
    for l in loans:
        bid = l["Book_ID"]
        borrow_count[bid] = borrow_count.get(bid, 0) + (1 if l["Operation_type"] == 1 else 0)

    most_borrowed_book = "-"
    most_borrowed_count = 0
    if borrow_count:
        top_bid = max(borrow_count, key=borrow_count.get)
        most_borrowed_count = borrow_count[top_bid]
        title = next((b["Book_Title"] for b in books if b["Book_ID"] == top_bid), "-")
        most_borrowed_book = f"{title} ({top_bid})"

    lines.append(f"- Most Borrowed Book : {most_borrowed_book} ({most_borrowed_count} times)")
    lines.append(f"- Currently Borrowed : {borrowed_now}")
    lines.append(f"- Active Members : {len([m for m in members if m['Member_status']==1])}")

    with open(REPORT_FILE, "w", encoding="utf-8") as rf:
        rf.write("\n".join(lines))
        rf.flush()
        os.fsync(rf.fileno())
    print(f"Report generated: {REPORT_FILE}")

def init_all_files():
    ensure_file(BOOKS_FILE, BOOK_STRUCT)
    ensure_file(MEMBERS_FILE, MEM_STRUCT)
    ensure_file(LOANS_FILE, LOAN_STRUCT)

# Menu
def main_menu():
    init_all_files()
    while True:
        print("\n===== Library Management =====")
        print("1. Add Book")
        print("2. Update Book")
        print("3. Delete Book")
        print("4. View Books")
        print("5. Add Member")
        print("6. Update Member")
        print("7. Delete Member")
        print("8. View Members")
        print("9. Borrow Book")
        print("10. Return Book")
        print("11. View Loans")
        print("12. Generate Report (.txt)")
        print("0. Exit")
        choice = input("Choose option: ").strip()
        if choice == "1":
            add_book()
        elif choice == "2":
            update_book()
        elif choice == "3":
            delete_book()
        elif choice == "4":
            view_books()
        elif choice == "5":
            add_member()
        elif choice == "6":
            update_member()
        elif choice == "7":
            delete_member()
        elif choice == "8":
            view_members()
        elif choice == "9":
            borrow_book()
        elif choice == "10":
            return_book()
        elif choice == "11":
            view_loans()
        elif choice == "12":
            generate_report()
        elif choice == "0":
            print("Exiting. Bye.")
            sys.exit(0)
        else:
            print("Invalid choice.")

if __name__ == "__main__":
    main_menu()
