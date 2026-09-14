"""Fayllar: har qanday tur yuklanadi va botda ochiladi.

Ikki muammo bor edi:
  * yuklashda tur bo'yicha oq ro'yxat turardi — .zip, .pptx, .csv, .heic rad etilardi;
  * web'dan yuklangan fayl botda umuman ko'rinmasdi — havola ham, tugma ham yo'q edi.
"""
import io

H = {"X-Service-Token": "test-service"}
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")


def _task(boss, world):
    return boss.post("/tasks", json={"title": "Fayl sinovi",
                                     "assignee_id": world["users"]["worker1"]["id"],
                                     "due_at": "2026-12-20"}).json()["id"]


def test_any_file_type_is_accepted(boss, world):
    """Ilgari bu turlarning hammasi «qabul qilinmaydi» deb rad etilardi."""
    tid = _task(boss, world)
    kinds = [
        ("reja.zip", b"PK\x03\x04zip", "application/zip"),
        ("taqdimot.pptx", b"PK\x03\x04pptx",
         "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("royxat.csv", b"a,b,c\n1,2,3", "text/csv"),
        ("surat.heic", b"\x00\x00\x00\x18ftypheic", "image/heic"),
        ("noma'lum.bin", b"\x00\x01\x02", "application/octet-stream"),
    ]
    for name, data, mime in kinds:
        r = boss.upload(f"/tasks/{tid}/files", files={"file": (name, data, mime)},
                        data={"kind": "task"})
        assert r.status_code == 201, f"{name} rad etildi: {r.text}"
        assert r.json()["filename"] == name


def test_size_is_still_the_limit(boss, world):
    """Tur cheklovi olib tashlandi, hajm esa qoladi."""
    tid = _task(boss, world)
    big = b"x" * (51 * 1024 * 1024)
    r = boss.upload(f"/tasks/{tid}/files", files={"file": ("katta.bin", big, "application/octet-stream")})
    assert r.status_code == 422 and r.json()["code"] == "FILE_TOO_LARGE", r.text


def test_files_are_always_served_as_a_download(boss, world, client):
    """Har qanday turni saqlash shu tufayli xavfsiz: brauzer ichidagini bajarmaydi."""
    tid = _task(boss, world)
    fid = boss.upload(f"/tasks/{tid}/files",
                      files={"file": ("sahifa.html", b"<script>alert(1)</script>", "text/html")},
                      data={"kind": "task"}).json()["id"]
    r = client.get(f"/files/{fid}/raw", headers=H)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_the_bot_can_fetch_the_file_itself(boss, world, client):
    """Bot faylni havola bilan emas, baytlari bilan oladi — domen va havola
    muddatiga bog'lanib qolmaslik uchun."""
    tid = _task(boss, world)
    fid = boss.upload(f"/tasks/{tid}/files", files={"file": ("dalil.png", PNG, "image/png")}).json()["id"]
    r = client.get(f"/files/{fid}/raw", headers=H)
    assert r.status_code == 200 and r.content == PNG

    assert client.get(f"/files/{fid}/raw").status_code == 401, "xizmat tokeni shart"
    assert client.get("/files/999999/raw", headers=H).status_code == 404


def test_task_reports_how_many_files_it_has(boss, world):
    """Botdagi «Fayllar» tugmasi shu songa qarab chiqadi. Web'dan qo'yilgan hujjat
    ham hisobga olinishi kerak — ilgari faqat dalillar sanalardi."""
    tid = _task(boss, world)
    boss.upload(f"/tasks/{tid}/files", files={"file": ("shartnoma.pdf", b"%PDF-1.4", "application/pdf")},
                data={"kind": "task"})
    boss.upload(f"/tasks/{tid}/files", files={"file": ("dalil.png", PNG, "image/png")},
                data={"kind": "proof"})
    tk = boss.get(f"/tasks/{tid}").json()
    assert tk["file_count"] == 2, "web'dan qo'yilgani ham sanalsin"
    assert tk["proof_count"] == 1
    assert len(tk["files"]) == 2 and all(f["url"] for f in tk["files"])
