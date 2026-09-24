export interface Device { udid: string; name: string; ios_version: string; trusted: boolean; product_type: string; model_id: string; model_number: string; serial: string; hardware: string; build: string; storage_total: number; storage_available: number; battery_pct: number; battery_charging: boolean; battery_eta_min: number | null; device_color: string; device_color_hex: string }
export interface AppInfo { bundle_id: string; name: string; file_sharing: boolean; installed: boolean }
export type SyncAction = 'push' | 'skip' | 'delete';
export interface SyncItem { filename: string; action: SyncAction; reason: string; size: number }
export interface SyncPreview { app_bundle_id: string; to_push: SyncItem[]; to_skip: SyncItem[]; to_delete: SyncItem[] }
export interface BackupInfo { udid: string; last_backup: string | null; encrypted: boolean; backup_dir?: string | null; available?: boolean; size_bytes?: number; file_count?: number; has_manifest?: boolean }
export interface BackupRecord { name: string; path: string; size_bytes: number; mtime: string | null; is_key_file: boolean }
export interface FileEntry { name: string; path: string; is_dir: boolean; size: number }
export interface PhotoItem { filename: string; path: string; size: number }
export interface PhotoDuplicateItem { filename: string; path: string; size: number }
export interface PhotoDuplicates { ok: boolean; udid: string; groups: PhotoDuplicateItem[][]; count: number; scanned: number; hashed: number; skipped: number; note?: string }
export interface StorageBreakdown { total: number; available: number; used: number; source: string }
export interface VerificationCheck { label: string; status: string; detail: string }
export interface Verification { udid: string; model_number: string; kind: string; refurbished_suspect: boolean; details: string[]; checks?: VerificationCheck[]; summary?: string }
export interface CrashItem { filename: string; size: number; app?: string; date?: string }
export interface SyslogResult { udid: string; lines: string; live: boolean; total?: number; shown?: number; errors?: number; warnings?: number; filtered?: boolean }
export interface FirmwareBuild { version: string; buildid: string; signed: boolean; url: string; filesize: number }
export interface ScreenHd { running: boolean; udid: string; url: string }
export interface ScreenAirplay { running: boolean; name: string; howto: string }
export interface ScreenStatus { udid: string; available: boolean; mode: string; live: boolean; developer_mode: string; needs: string[]; ios_version: string; backends: { pymobiledevice3: boolean; idevicescreenshot: boolean; uxplay: boolean }; hd: ScreenHd; airplay: ScreenAirplay; hints: { pymobiledevice3: string; uxplay: string } }
