# Playlist Offline

App desktop phát nhạc offline từ thư mục `/home/kevin/Music/Nhac_Viet`.

## Chạy app

```sh
./run_playlist_app.sh
```

Nếu muốn đổi thư mục nhạc, vào menu `Thư viện > Chọn thư mục nhạc`.

App có cửa sổ Now Playing và hỗ trợ điều khiển media trên thanh thông báo của hệ điều hành qua MPRIS.

## Cấu trúc code

- `music_player.py`: file chạy app.
- `player_window.py`: cửa sổ chính, danh sách bài, play/pause, tìm kiếm.
- `now_playing.py`: cửa sổ Now Playing.
- `mpris.py`: điều khiển media trên thanh thông báo hệ điều hành.
- `library.py`: quét thư viện nhạc, album, artwork.
- `i18n.py`: nội dung tiếng Việt/tiếng Anh.
- `constants.py`: cấu hình chung.
- `utils.py`: hàm tiện ích nhỏ.
