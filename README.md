# SW Mates – lắp ghép kiểu SolidWorks cho Autodesk Fusion

Add-in Python cho **Autodesk Fusion (Fusion 360)**, giúp lắp ghép chi tiết trong assembly
giống với lệnh **Mate** của SolidWorks:

- Chọn **2 đối tượng** (mặt, cạnh, điểm, joint origin) trên 2 component. Như SolidWorks,
  component chứa **đối tượng thứ nhất sẽ di chuyển**.
- Chọn loại **mate chuẩn**: Coincident, Parallel, Perpendicular, Concentric, Lock, Distance, Angle.
  Add-in tự gợi ý loại mate phù hợp với hình học đã chọn (giống thanh mate pop-up của SolidWorks).
- Có **Aligned / Anti-Aligned**, **Flip dimension**, **Lock rotation**, và **pushpin**
  (giữ hộp thoại để mate liên tục).
- **Ghép nhiều mate**: các mate giữa cùng một cặp component được gộp tự động thành **một
  Fusion joint** với số bậc tự do (DOF) đúng, ví dụ *Concentric + Coincident → Revolute*.
- **Mate Manager**: xem danh sách mate của từng cặp component, xóa từng mate (joint được
  dựng lại từ các mate còn lại), giống thư mục *Mates* trong cây FeatureManager.

> Vì sao không dùng thẳng "Assembly Constraints" mới của Fusion? Tính năng *Constrain
> Components* (2025) có API nhưng đang ở trạng thái **Preview** và Autodesk đã thông báo
> sẽ thay thế toàn bộ, không nên dùng cho công cụ lâu dài. Add-in này dựa trên **Joint
> API** ổn định, nên chạy được trên mọi bản Fusion hiện tại.

## Cài đặt

1. Tải/clone repo này, lấy thư mục `SWMates/`.
2. Trong Fusion: **Utilities → Add-Ins → Scripts and Add-Ins** (phím tắt `Shift+S`),
   tab **Add-Ins**, bấm **+** cạnh *My Add-Ins* và chọn thư mục `SWMates`.
   (Hoặc chép thư mục `SWMates` vào
   `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns` trên Windows /
   `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns` trên macOS.)
3. Chọn **SWMates** → **Run**. Tích *Run on Startup* để tự chạy khi mở Fusion.
4. Hai lệnh **Mate (SolidWorks)** và **Mate Manager** xuất hiện ở
   **Design → Solid → Assemble** (lệnh Mate được ghim sẵn lên thanh công cụ).

Mẹo: gán phím tắt `M` cho lệnh Mate (rê chuột lên lệnh → menu *…* → *Change Keyboard
Shortcut*) để thao tác giống SolidWorks.

## Cách dùng

1. Mở assembly có ít nhất 2 component (body phải nằm trong component, không ở root).
2. Chạy **Mate (SolidWorks)**.
3. Chọn đối tượng trên component **cần di chuyển**, rồi đối tượng trên component kia
   (đối tượng thứ 2 bắt buộc thuộc component khác – add-in tự chặn chọn sai).
4. Kiểm tra loại mate được gợi ý, chỉnh Alignment / khoảng cách / góc nếu cần. Ô trạng
   thái cho biết **Fusion joint sẽ được tạo** và số bậc tự do còn lại; preview hiển thị
   ngay trên màn hình.
5. Bấm **Mate**. Bật *Giữ hộp thoại (pushpin)* để tiếp tục mate mà không phải mở lại lệnh.

### Mate đơn lẻ → Fusion joint

| Mate (SolidWorks)          | Hình học chọn                           | Fusion joint tạo ra                     |
|----------------------------|-----------------------------------------|-----------------------------------------|
| Coincident                 | mặt phẳng – mặt phẳng (hoặc cạnh tròn)  | Planar (3 DOF)                          |
| Coincident                 | cạnh tròn – cạnh tròn                   | Revolute (đồng tâm + áp mặt, "peg-in-hole") |
| Coincident                 | trục – trục (cạnh thẳng)                | Cylindrical                             |
| Coincident                 | điểm – điểm                             | Ball                                    |
| Coincident                 | joint origin – joint origin             | Rigid                                   |
| Concentric                 | mặt trụ/côn, cạnh tròn, trục            | Cylindrical (2 DOF)                     |
| Concentric + Lock rotation | như trên                                | Slider                                  |
| Concentric                 | mặt cầu – mặt cầu/điểm                  | Ball                                    |
| Distance                   | mặt phẳng – mặt phẳng                   | Planar có offset                        |
| Distance                   | cạnh tròn – cạnh tròn                   | Revolute có offset                      |
| Lock                       | bất kỳ                                  | As-built Rigid (khóa tại vị trí hiện tại) |

### Gộp nhiều mate giữa cùng một cặp component

Mate có trục (Concentric / cạnh tròn) được dùng làm **mate gốc**; các mate thêm vào sẽ
khóa dần bậc tự do *xoay* và *trượt* quanh trục đó:

| Tổ hợp mate                                                       | Kết quả     |
|-------------------------------------------------------------------|-------------|
| Concentric + Coincident/Distance (mặt ⟂ trục)                     | Revolute    |
| Concentric + Coincident (mặt ∥ trục), Parallel, Perpendicular, Angle | Slider   |
| Concentric + Concentric (2 trục song song, ví dụ 2 chốt)           | Slider      |
| Concentric + Coincident (mặt ⟂ trục) + Parallel/Angle/chốt thứ 2   | Rigid       |
| Cạnh tròn Coincident + Parallel / Angle / Perpendicular            | Rigid       |
| Lock (thay thế mọi mate trước đó)                                  | As-built Rigid |

Thứ tự thêm mate không quan trọng – mate gốc được chọn theo độ ưu tiên
(cạnh tròn > trục > mặt phẳng > điểm). Mate thứ hai khóa lại bậc tự do đã bị khóa sẽ báo
**over-defined** giống SolidWorks.

Kỹ thuật: joint được tạo từ mate gốc, sau đó add-in **đo hình học thực tế** và tự chỉnh
tham số `offset`/`angle` của joint (phương pháp cát tuyến) cho đến khi các mate còn lại
thỏa mãn. Danh sách mate được lưu trong *attributes* của joint nên vẫn còn sau khi lưu
và mở lại file.

## Giới hạn hiện tại

Fusion chỉ có joint (mỗi cặp component một quan hệ chuyển động) chứ không có bộ giải ràng
buộc tổng quát như SolidWorks, vì vậy:

- **Chưa hỗ trợ**: Tangent, Width, Symmetric, Path, Cam, Gear, Rack-Pinion, Limit mates.
- Tổ hợp **2–3 mặt phẳng không song song** (ví dụ áp hộp vào góc) chưa gộp được; hãy
  dùng Concentric hoặc Lock.
- Parallel / Perpendicular / Angle **không đứng một mình** được – cần có mate trục trước.
- Mate *Coincident* mặt–mặt đặt tâm hai mặt trùng nhau ban đầu (chi tiết vẫn trượt tự do
  trong mặt phẳng), khác SolidWorks là giữ nguyên vị trí.
- Khi trục được chọn là **cạnh thẳng**, việc căn offset dọc trục có thể không chính xác;
  nên chọn mặt trụ hoặc cạnh tròn.
- Mate giữa các cặp component khác nhau được giải độc lập bởi Fusion (giống joint thông
  thường).
- Add-in được viết theo tài liệu Fusion API và đã kiểm thử phần logic bằng unit test, nhưng
  **chưa được chạy thử trong Fusion** – nếu gặp lỗi xin báo lại kèm thông báo lỗi.

## Cấu trúc mã nguồn

```
SWMates/
├── SWMates.py, SWMates.manifest   # điểm vào của add-in
├── core/                          # logic thuần Python (không phụ thuộc Fusion, có unit test)
│   ├── vec.py                     # toán vector
│   └── mates.py                   # loại mate, gộp mate → kế hoạch joint, phép đo & mục tiêu
├── bridge/                        # làm việc với Fusion API
│   ├── features.py                # đối tượng được chọn → hình học (mặt, trục, điểm...)
│   ├── joints.py                  # tạo joint, căn offset/angle, gộp & dựng lại
│   └── storage.py                 # lưu danh sách mate trong attributes của joint
├── commands/
│   ├── mate_cmd.py                # lệnh Mate (giao diện giống SolidWorks)
│   └── manager_cmd.py             # lệnh Mate Manager
└── resources/                     # icon (tạo bằng tools/make_icons.py)
tests/                             # pytest cho core/ và bộ giải
```

## Chạy test

```bash
pip install pytest
python -m pytest tests
```
