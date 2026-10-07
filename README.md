# FinViet Pro — Ứng dụng phân tích đầu tư chứng khoán Việt Nam

Ứng dụng web (Python Flask + SQLite) phân tích kỹ thuật cổ phiếu Việt Nam theo phương pháp
**Fibonacci · Pivot Point · Hỗ trợ/Kháng cự**, quản trị vốn theo **Kelly 1/2 của Edward Thorp**,
kèm **quản lý danh mục — cảnh báo tự động** và **sàng lọc cổ phiếu theo tín hiệu mua & cổ tức**.
Dữ liệu lấy từ **Vietcap Trading API** (giá EOD, chỉ số, cổ tức).

![FinViet Pro](https://img.shields.io/badge/Python-Flask-38bdf8) ![DB](https://img.shields.io/badge/Storage-SQLite-16c784)

---

## 1. Chức năng chính

| Nhóm chức năng | Chi tiết |
| --- | --- |
| **Tìm điểm mua/bán** | Fibonacci thoái lui (0.236–0.786) + vùng vàng 0.5–0.618, Fibonacci mở rộng (1.272/1.618), Pivot Point (ngày/tuần/tháng), hỗ trợ/kháng cự theo cụm đỉnh-đáy, RSI/MACD/MA/Bollinger/ATR |
| **Tín hiệu mua-bán** | Điểm tổng hợp −100…+100 với 5 mức: MUA MẠNH / MUA / NẮM GIỮ / BÁN / BÁN MẠNH, kèm lý do cụ thể |
| **Điểm hành động** | Vùng mua (buy zone), các mức mua theo Fib/Pivot/hỗ trợ, **cắt lỗ theo ATR**, các mức chốt lời, tỷ lệ R:R và cảnh báo rủi ro |
| **Quản trị vốn Kelly 1/2** | \(f^* = p - \dfrac{q}{b}\) (p: xác suất thắng, b: payoff) · dùng **1/2 Kelly** theo Edward Thorp · khối lượng = min(Kelly, rủi ro %/lệnh, tỷ trọng tối đa) · làm tròn theo lô 100 CP |
| **Kiểm định lịch sử (backtest)** | Mô phỏng vào lệnh khi điểm ≥ +30, cắt lỗ 1.5×ATR, mục tiêu 2R — cho ra win-rate, payoff, kỳ vọng làm đầu vào cho Kelly |
| **Quản lý danh mục** | Vị thế (giá vốn, KL, cắt lỗ, chốt lời), lãi/lỗ realtime theo giá đóng cửa, phân bổ tỷ trọng, danh sách theo dõi |
| **Cảnh báo tự động** | Cắt lỗ chạm ngưỡng, tín hiệu bán, chốt lời, chốt lãi chủ động (>8% từ đỉnh), thủng hỗ trợ, tín hiệu mua cho mã theo dõi, đạt giá mục tiêu — chống trùng lặp theo ngày |
| **Sàng lọc cổ phiếu** | Quét nền theo nhóm chỉ số (VN30/VN100/HNX30/HOSE/HNX/UPCOM/ETF), sàn, hoặc danh sách tự chọn · lọc theo tín hiệu, điểm, thanh khoản, giá, **tỷ suất cổ tức ≥ ngưỡng** · thanh tiến độ realtime · xuất CSV |
| **Lưu trữ SQLite** | Toàn bộ dữ liệu (nến, cơ bản, cổ tức, kết quả phân tích, phiên sàng lọc, vị thế, cảnh báo, cài đặt) lưu trong `data/fintech.db` — có bộ đệm giảm gọi API |

## 2. Cài đặt & chạy

Yêu cầu: **Python 3.10+** (khuyến nghị 3.12+).

```bash
# 1. Cài thư viện (chỉ cần Flask — phần còn lại dùng thư viện chuẩn)
pip install -r requirements.txt

# 2. Chạy ứng dụng
python app.py
```

Hoặc trên Windows: nháy đúp **`run.bat`** (tự cài Flask nếu thiếu và tự mở trình duyệt).

Mở trình duyệt: **http://127.0.0.1:5000**

Biến môi trường tùy chọn: `FINTECH_HOST` (mặc định 127.0.0.1), `FINTECH_PORT` (mặc định 5000), `FINTECH_DEBUG=1`.

## 3. Hướng dẫn sử dụng

1. **Tổng quan** — VNINDEX/VN30, giá trị danh mục, cảnh báo mới, cơ hội mua từ lần sàng lọc gần nhất.
2. **Phân tích kỹ thuật** — Nhập mã (VD `FPT`) → biểu đồ nến với lưới Fibonacci (vùng vàng tô sáng),
   Pivot, hỗ trợ/kháng cự, **mũi tên MUA/BÁN** theo tín hiệu lịch sử; thẻ hành động (mua – cắt lỗ – chốt lời – R:R);
   **máy tính Kelly 1/2** tự điền số liệu từ backtest; bảng Fib/Pivot/S-R; cổ tức & cổ tức 12 tháng.
3. **Sàng lọc cổ phiếu** — Chọn vũ trụ quét + tiêu chí (tín hiệu, điểm tối thiểu, cổ tức ≥ %, thanh khoản, giá)
   → bấm **Bắt đầu sàng lọc**, theo dõi tiến độ; kết quả gồm giá, RSI, vùng mua, cắt lỗ, mục tiêu, R:R; xuất CSV.
   *Ví dụ lọc cổ tức: nhập `6` ở ô "Cổ tức tối thiểu" nghĩa là giữ lại mã có cổ tức tiền mặt ≥ 6% thị giá.*
4. **Danh mục đầu tư** — Thêm vị thế (nút *Gợi ý giá & cắt lỗ theo phân tích* tự lấy cắt lỗ theo ATR/Fib),
   theo dõi lãi/lỗ, phân bổ, danh sách theo dõi; nút **Quét cảnh báo ngay**.
5. **Cảnh báo** — Lọc theo mức độ/mã, đánh dấu đã xem, quét lại.
6. **Cài đặt** — Vốn, chế độ Kelly (1/2 hoặc đầy đủ), rủi ro %/lệnh, tỷ trọng tối đa, lô giao dịch,
   số phiên lịch sử, hạn bộ đệm, tần suất quét, làm mới danh sách mã từ Vietcap.

## 4. Phương pháp tính

- **Fibonacci**: xác định swing cao–thấp trong ~160 phiên, tính thoái lui theo hướng xu hướng
  (`UP`: Fib là hỗ trợ — mua khi về vùng vàng; `DOWN`: Fib là kháng cự — ưu tiên đứng ngoài/chờ tạo đáy).
- **Pivot Point** cổ điển: `P = (H+L+C)/3`, `R1 = 2P−L`, `S1 = 2P−H`, R2/S2, R3/S3 — theo phiên, tuần, tháng đã đóng.
- **Hỗ trợ/Kháng cự**: gom cụm đỉnh-đáy fractal (k=3) trong ~220 phiên, dung sai `max(0.8% giá, 0.6×ATR)`, ưu tiên mức gần & nhiều lần chạm.
- **Điểm tín hiệu**: tổng hợp xu hướng (±30), động lượng RSI/MACD (±26), vị trí so với Fib/Pivot/S-R (±30), thanh khoản (±8), pivot (±8).
- **Cắt lỗ**: mức hỗ trợ gần hoặc `giá − 1.5×ATR` (chọn mức hợp lý hơn); **chốt lời**: kháng cự gần, Fib mở rộng, mục tiêu 2R.
- **Kelly 1/2**: `f* = p − q/b`; khối lượng đề xuất = min(khối lượng Kelly × 1/2, khối lượng theo rủi ro %/lệnh, khối lượng theo tỷ trọng tối đa), làm tròn lô 100.

## 5. Nguồn dữ liệu (Vietcap)

- `GET /api/price/symbols/getAll` — danh sách niêm yết
- `GET /api/price/symbols/getByGroup?group=VN30|VN100|HNX30|HOSE|HNX|UPCOM|ETF` — nhóm mã
- `POST /api/chart/OHLCChart/gap-chart` — lịch sử nến ngày (`o,h,l,c,v,t`)
- `iq.vietcap.com.vn/api/iq-insight-service/v1/company/details` — cơ bản, cổ tức 12 tháng (`dividendPerShareTsr`)
- `iq.vietcap.com.vn/api/iq-insight-service/v1/events?...eventCode=DIV` — lịch sử cổ tức

Dữ liệu được **đệm trong SQLite** (nến 6 giờ, cơ bản 24 giờ, danh sách mã 72 giờ — tùy chỉnh ở trang Cài đặt).

## 6. Cấu trúc dự án

```
fintech/
├── app.py                  # điểm khởi động (local)
├── api/index.py            # entrypoint serverless cho Vercel
├── vercel.json             # cấu hình deploy Vercel (rewrites + functions)
├── requirements.txt
├── run.bat
├── data/fintech.db         # SQLite (tự tạo khi chạy local)
├── tools/
│   ├── api_probe.py        # công cụ kiểm tra API Vietcap
│   └── smoke_test.py       # kiểm thử đầu-cuối (server đang chạy)
└── fintech/
    ├── config.py           # hằng số, ngưỡng tín hiệu, cài đặt mặc định (tự nhận diện Vercel)
    ├── db.py               # schema + truy vấn SQLite
    ├── vietcap.py          # client Vietcap (retry, semaphore)
    ├── indicators.py       # SMA/EMA/RSI/MACD/ATR/Bollinger
    ├── analysis.py         # Fib, Pivot, S/R, điểm tín hiệu, backtest, mức hành động
    ├── kelly.py            # Kelly 1/2 + định cỡ vị thế
    ├── market.py           # dịch vụ dữ liệu + bộ đệm
    ├── portfolio.py        # vị thế, theo dõi, engine cảnh báo
    ├── screener.py         # quét nền đa luồng + lọc cổ tức/tín hiệu
    ├── routes.py           # trang + REST API
    ├── templates/          # dashboard, phân tích, sàng lọc, danh mục, cảnh báo, cài đặt
    └── static/             # CSS theme fintech tối + JS (biểu đồ TradingView lightweight-charts)
```

## 7. Kiểm thử

```bash
python app.py                 # cửa sổ 1
python tools/smoke_test.py    # cửa sổ 2 — kiểm thử 29 mục: trang, phân tích, Kelly, sàng lọc, danh mục, cảnh báo
```

## 8. Triển khai lên Vercel

Dự án đã được đóng gói sẵn cho Vercel (serverless):

- **`api/index.py`** — entrypoint WSGI mà runtime `@vercel/python` tự nhận diện.
- **`vercel.json`** — định tuyến mọi request vào hàm Flask (`rewrites`), cấu hình
  `maxDuration: 60s` và `includeFiles: fintech/**` để đóng gói templates/static.
- **`.vercelignore`** — loại `data/`, `tools/`, bộ đệm khỏi bundle.
- **`fintech/config.py`** — tự nhận diện `VERCEL=1`: chuyển SQLite sang `/tmp/finviet-pro`
  (vì hệ thống tệp trên Vercel chỉ ghi được ở `/tmp`).

### Cách 1: Vercel CLI

```bash
npm i -g vercel      # cài CLI (một lần)
vercel login         # đăng nhập
vercel               # deploy bản preview
vercel --prod        # deploy production
```

### Cách 2: GitHub

Push mã nguồn lên GitHub → vào [vercel.com/new](https://vercel.com/new) → Import repository →
giữ nguyên cấu hình mặc định (Vercel tự đọc `vercel.json` + `requirements.txt`) → Deploy.

### Lưu ý quan trọng khi chạy trên Vercel (serverless)

| Vấn đề | Hệ quả | Khắc phục |
| --- | --- | --- |
| Hệ thống tệp chỉ ghi được `/tmp`, **không bền vững** | Vị thế, cảnh báo, cài đặt, lịch sử sàng lọc có thể **mất khi cold start** hoặc đổi instance | Phù hợp demo; muốn lưu lâu dài hãy deploy lên VPS/Render/Railway (SQLite nguyên vẹn) hoặc đặt biến `FINTECH_DATA_DIR` trỏ tới ổ đĩa bền vững |
| Hàm bị giới hạn thời gian (`maxDuration: 60`) | Sàng lọc/ quét danh mục lớn có thể bị cắt giữa chừng | Chỉ nên sàng lọc danh sách nhỏ (≤ 50 mã); phiên chạy dang dở tự chuyển `ERROR` sau 30 phút |
| Instance ngủ sau khi trả response | Cảnh báo "quét tự động" chỉ chạy khi có request | Bấm **Quét danh mục** trên web để quét theo nhu cầu |
| Cold start | Request đầu tiên chậm vài giây | Bình thường với serverless |
| Cần Internet ra ngoài | Không truy cập được Vietcap = không có dữ liệu | Kiểm tra bằng `GET /api/health` (trả về `"serverless": true`) |

### Kiểm tra sau khi deploy

```bash
curl https://<ten-app>.vercel.app/api/health
# {"status":"ok","app":"FinViet Pro","serverless":true,"storage":"ephemeral",...}
```

---

> ⚠️ **Miễn trừ trách nhiệm**: FinViet Pro là công cụ phân tích tham khảo, **không phải khuyến nghị đầu tư**.
> Dữ liệu giá là EOD từ Vietcap, có thể chậm/thiếu; hãy tự kiểm chứng trước khi giao dịch.
