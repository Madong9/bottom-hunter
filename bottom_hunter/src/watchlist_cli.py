from __future__ import annotations

import argparse
import json
from pathlib import Path

from .account_watchlist import SOURCE_LABELS, AccountWatchlistRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="账号自选导入、去重与动态行业板块生成")
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser("import", help="导入某一账号导出的自选文件")
    importer.add_argument("--source", required=True, choices=tuple(SOURCE_LABELS))
    importer.add_argument("--file", required=True, type=Path)
    importer.add_argument("--account", default="", help="账号别名（不是密码）")
    importer.add_argument("--no-resolve", action="store_true", help="不联网尝试补全行业")

    commands.add_parser("rebuild", help="从三个已保存快照重建活动观察池")
    commands.add_parser("sync", help="重新读取之前关联的导出文件")
    commands.add_parser("status", help="显示账号来源与合并统计")

    industry = commands.add_parser("set-industry", help="人工修正一个股票的行业")
    industry.add_argument("canonical_id")
    industry.add_argument("industry")

    clear = commands.add_parser("clear", help="清空某一账号来源快照")
    clear.add_argument("--source", required=True, choices=tuple(SOURCE_LABELS))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository = AccountWatchlistRepository()
    if args.command == "import":
        result = repository.import_file(
            args.source,
            args.file,
            args.account,
            resolve_industries=not args.no_resolve,
        )
        print(
            f"[{SOURCE_LABELS[result.source]}] 导入 {result.imported_count} 项；"
            f"合并后 {result.merged_count} 项，跨平台重合 {result.duplicate_count} 项，"
            f"生成 {result.generated_sector_count} 个检测板块。"
        )
        if result.unresolved_industry_count:
            print(f"尚有 {result.unresolved_industry_count} 只股票需要确认行业。")
        if result.skipped_count:
            print(f"已跳过 {result.skipped_count} 条不支持或无效的记录。")
            for warning in result.warnings[:5]:
                print(f"- {warning}")
        print(result.active_watchlist)
        return 0
    if args.command == "rebuild":
        summary = repository.rebuild_active_watchlist()
    elif args.command == "sync":
        summary, refreshed, errors = repository.refresh_linked_files()
        print(
            "已同步："
            + (", ".join(SOURCE_LABELS[source] for source in refreshed) if refreshed else "无")
        )
        for source, error in errors.items():
            print(f"[{SOURCE_LABELS[source]}] {error}")
    elif args.command == "set-industry":
        summary = repository.update_industry(args.canonical_id, args.industry)
    elif args.command == "clear":
        summary = repository.clear_source(args.source)
    else:
        summary = repository.summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
