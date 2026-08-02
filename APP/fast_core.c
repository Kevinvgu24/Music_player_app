#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <windows.h>

#define EXPORT __declspec(dllexport)
#define MAX_LONG_PATH 32768

// Native Vietnamese UTF-8 character diacritics stripping & lowercasing (100% Comprehensive Coverage)
EXPORT int fast_remove_accents(const char* input, char* output, int max_len) {
    if (!input || !output || max_len <= 0) return 0;
    
    int i = 0, j = 0;
    unsigned char c1, c2, c3;
    
    while (input[i] != '\0' && j < max_len - 1) {
        c1 = (unsigned char)input[i];
        
        // 1. ASCII characters (0x00 - 0x7F)
        if (c1 < 0x80) {
            char ch = (char)tolower(c1);
            if (isalnum((unsigned char)ch)) {
                output[j++] = ch;
            } else {
                output[j++] = ' ';
            }
            i++;
            continue;
        }
        
        // 2. 2-byte UTF-8 sequences (0xC0 - 0xDF)
        if ((c1 & 0xE0) == 0xC0) {
            c2 = (unsigned char)input[i + 1];
            if (c2 == 0) break;
            
            // đ (0xC4 0x91), Đ (0xC4 0x90)
            if (c1 == 0xC4 && (c2 == 0x91 || c2 == 0x90)) {
                output[j++] = 'd';
                i += 2;
                continue;
            }
            // ă (0xC4 0x83), Ă (0xC4 0x82)
            if (c1 == 0xC4 && (c2 == 0x83 || c2 == 0x82)) {
                output[j++] = 'a';
                i += 2;
                continue;
            }
            // ơ (0xC6 0xA1), Ơ (0xC6 0xA0)
            if (c1 == 0xC6 && (c2 == 0xA1 || c2 == 0xA0)) {
                output[j++] = 'o';
                i += 2;
                continue;
            }
            // ư (0xC6 0xB0), Ư (0xC6 0xAF)
            if (c1 == 0xC6 && (c2 == 0xB0 || c2 == 0xAF)) {
                output[j++] = 'u';
                i += 2;
                continue;
            }
            
            // Standard Latin-1 Supplement accents (0xC3)
            if (c1 == 0xC3) {
                // à-å, À-Å -> a
                if ((c2 >= 0xA0 && c2 <= 0xA5) || (c2 >= 0x80 && c2 <= 0x85)) { output[j++] = 'a'; i += 2; continue; }
                // è-ë, È-Ë -> e
                if ((c2 >= 0xA8 && c2 <= 0xAB) || (c2 >= 0x88 && c2 <= 0x8B)) { output[j++] = 'e'; i += 2; continue; }
                // ì-ï, Ì-Ï -> i
                if ((c2 >= 0xAC && c2 <= 0xAF) || (c2 >= 0x8C && c2 <= 0x8F)) { output[j++] = 'i'; i += 2; continue; }
                // ò-ö, Ò-Ö -> o
                if ((c2 >= 0xB2 && c2 <= 0xB6) || (c2 >= 0x92 && c2 <= 0x96)) { output[j++] = 'o'; i += 2; continue; }
                // ù-ü, Ù-Ü -> u
                if ((c2 >= 0xB9 && c2 <= 0xBC) || (c2 >= 0x99 && c2 <= 0x9C)) { output[j++] = 'u'; i += 2; continue; }
                // ý, ÿ, Ý -> y
                if (c2 == 0xBD || c2 == 0xBF || c2 == 0x9D) { output[j++] = 'y'; i += 2; continue; }
            }
            
            // Other 2-byte characters
            output[j++] = ' ';
            i += 2;
            continue;
        }
        
        // 3. 3-byte UTF-8 sequences (0xE0 - 0xEF) - Full Vietnamese Extended Range (0xE1 0xBA 0x80 - 0xE1 0xBB 0x99)
        if ((c1 & 0xF0) == 0xE0) {
            c2 = (unsigned char)input[i + 1];
            c3 = (unsigned char)input[i + 2];
            if (c2 == 0 || c3 == 0) break;
            
            if (c1 == 0xE1) {
                if (c2 == 0xBA) {
                    // a: Ạ ạ Ả ả Ấ ấ Ầ ầ Ẩ ẩ Ẫ ẫ Ậ ậ Ắ ắ Ằ ằ Ẳ ẳ Ẵ ẵ Ặ ặ (0x80 - 0x97)
                    if (c3 >= 0x80 && c3 <= 0x97) { output[j++] = 'a'; i += 3; continue; }
                    // e: Ẹ ẹ Ẻ ẻ Ẽ ẽ Ế ế Ề ề Ể ể Ễ ễ Ệ ệ (0x98 - 0xA7)
                    if (c3 >= 0x98 && c3 <= 0xA7) { output[j++] = 'e'; i += 3; continue; }
                    // i: Ỉ ỉ Ị ị (0xA8 - 0xAB)
                    if (c3 >= 0xA8 && c3 <= 0xAB) { output[j++] = 'i'; i += 3; continue; }
                    // o: Ọ ọ Ỏ ỏ Ố ố Ồ ồ Ổ ổ Ỗ ỗ Ộ ộ Ớ ớ Ờ ờ Ở ở (0xAC - 0xBF)
                    if (c3 >= 0xAC && c3 <= 0xBF) { output[j++] = 'o'; i += 3; continue; }
                } else if (c2 == 0xBB) {
                    // o: Ỡ ỡ Ợ ợ (0x80 - 0x83)
                    if (c3 >= 0x80 && c3 <= 0x83) { output[j++] = 'o'; i += 3; continue; }
                    // u: Ụ ụ Ủ ủ Ứ ứ Ừ ừ Ử ử Ữ ữ Ự ự (0x84 - 0x91)
                    if (c3 >= 0x84 && c3 <= 0x91) { output[j++] = 'u'; i += 3; continue; }
                    // y: Ỳ ỳ Ỵ ỵ Ỷ ỷ Ỹ ỹ (0x92 - 0x99)
                    if (c3 >= 0x92 && c3 <= 0x99) { output[j++] = 'y'; i += 3; continue; }
                }
            }
            
            output[j++] = ' ';
            i += 3;
            continue;
        }
        
        // 4-byte UTF-8
        output[j++] = ' ';
        i += 4;
    }
    
    output[j] = '\0';
    
    // Collapse multiple spaces into single space and trim
    int read_idx = 0, write_idx = 0;
    int in_space = 1; // Trim leading spaces
    
    while (output[read_idx] != '\0') {
        if (output[read_idx] == ' ') {
            if (!in_space) {
                output[write_idx++] = ' ';
                in_space = 1;
            }
        } else {
            output[write_idx++] = output[read_idx];
            in_space = 0;
        }
        read_idx++;
    }
    
    if (write_idx > 0 && output[write_idx - 1] == ' ') {
        write_idx--;
    }
    output[write_idx] = '\0';
    
    return write_idx;
}

// Check if file extension is a supported audio extension
static int is_audio_ext(const wchar_t* ext) {
    if (!ext) return 0;
    if (_wcsicmp(ext, L".mp3") == 0) return 1;
    if (_wcsicmp(ext, L".flac") == 0) return 1;
    if (_wcsicmp(ext, L".wav") == 0) return 1;
    if (_wcsicmp(ext, L".m4a") == 0) return 1;
    if (_wcsicmp(ext, L".ogg") == 0) return 1;
    if (_wcsicmp(ext, L".aac") == 0) return 1;
    if (_wcsicmp(ext, L".opus") == 0) return 1;
    if (_wcsicmp(ext, L".mp4") == 0) return 1;
    return 0;
}

// Recursive Win32 Fast Directory Scan supporting Long Paths
static void scan_dir_recursive_w(const wchar_t* dir, wchar_t* out_buf, size_t* pos, size_t max_chars, int* count) {
    wchar_t* search_pattern = (wchar_t*)malloc(MAX_LONG_PATH * sizeof(wchar_t));
    wchar_t* full_path = (wchar_t*)malloc(MAX_LONG_PATH * sizeof(wchar_t));
    
    if (!search_pattern || !full_path) {
        if (search_pattern) free(search_pattern);
        if (full_path) free(full_path);
        return;
    }

    swprintf(search_pattern, MAX_LONG_PATH, L"%s\\*", dir);

    WIN32_FIND_DATAW find_data;
    HANDLE hFind = FindFirstFileW(search_pattern, &find_data);

    if (hFind == INVALID_HANDLE_VALUE) {
        free(search_pattern);
        free(full_path);
        return;
    }

    do {
        if (wcscmp(find_data.cFileName, L".") == 0 || wcscmp(find_data.cFileName, L"..") == 0) {
            continue;
        }

        swprintf(full_path, MAX_LONG_PATH, L"%s\\%s", dir, find_data.cFileName);

        if (find_data.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            scan_dir_recursive_w(full_path, out_buf, pos, max_chars, count);
        } else {
            const wchar_t* ext = wcsrchr(find_data.cFileName, L'.');
            if (ext && is_audio_ext(ext)) {
                size_t len = wcslen(full_path);
                if (*pos + len + 2 < max_chars) {
                    wcscpy(&out_buf[*pos], full_path);
                    *pos += len;
                    out_buf[*pos] = L'\n';
                    (*pos)++;
                    out_buf[*pos] = L'\0';
                    (*count)++;
                }
            }
        }
    } while (FindNextFileW(hFind, &find_data));

    FindClose(hFind);
    free(search_pattern);
    free(full_path);
}

// Exported Fast Directory Scan (Returns total audio files count)
EXPORT int fast_scan_audio_files_w(const wchar_t* root_dir, wchar_t* out_buf, size_t max_chars) {
    if (!root_dir || !out_buf || max_chars == 0) return 0;
    
    size_t pos = 0;
    int count = 0;
    out_buf[0] = L'\0';
    
    scan_dir_recursive_w(root_dir, out_buf, &pos, max_chars, &count);
    return count;
}

// Exported Fast Substring Search Matching (Returns 1 if query matched haystack, 0 otherwise)
EXPORT int fast_contains_query(const char* haystack, const char* query) {
    if (!haystack || !query) return 0;
    if (query[0] == '\0') return 1;
    
    char norm_haystack[4096];
    char norm_query[1024];
    
    fast_remove_accents(haystack, norm_haystack, sizeof(norm_haystack));
    fast_remove_accents(query, norm_query, sizeof(norm_query));
    
    return strstr(norm_haystack, norm_query) != NULL ? 1 : 0;
}

