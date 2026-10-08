#!/usr/bin/env python3
"""配置固定版本的 Android 包装项目，使用独立的分支包名和签名。"""

import argparse
import json
import re
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one occurrence of {old!r}")
    return text.replace(old, new, 1)


def prepare(repo, android):
    version = json.loads((repo / "app/package.json").read_text(encoding="utf-8"))["version"]
    root_gradle = android / "build.gradle"
    root_text = root_gradle.read_text(encoding="utf-8")
    match = re.search(r'^\s*siyuanVersionName\s*=\s*"([^"]+)"\s*$', root_text, re.MULTILINE)
    if not match or match.group(1) != version:
        raise ValueError(f"Android wrapper version must match fork version {version}")

    app_gradle = android / "app/build.gradle"
    app_text = app_gradle.read_text(encoding="utf-8")
    app_text = replace_once(app_text, 'applicationId "org.b3log.siyuan"',
                            'applicationId "org.b3log.siyuan.fork"')
    app_text = replace_once(app_text, 'resValue "string", "app_package_name", "org.b3log.siyuan"',
                            'resValue "string", "app_package_name", "org.b3log.siyuan.fork"')
    app_text = replace_once(app_text, 'resValue "string", "app_package_name", "org.b3log.siyuan.debug"',
                            'resValue "string", "app_package_name", "org.b3log.siyuan.fork.debug"')
    app_text = replace_once(app_text, 'resValue "string", "app_name", "SiYuan-Debug"',
                            'resValue "string", "app_name", "SiYuan Fork Debug"')
    app_text = replace_once(app_text, 'resValue "string", "app_package_name", "org.b3log.siyuan.fork"',
                            'resValue "string", "app_package_name", "org.b3log.siyuan.fork"\n'
                            '            resValue "string", "app_name", "SiYuan Fork"')

    manifest = android / "app/src/main/AndroidManifest.xml"
    manifest_text = replace_once(manifest.read_text(encoding="utf-8"),
                                 'android:taskAffinity="org.b3log.siyuan.shorthand"',
                                 'android:taskAffinity="${applicationId}.shorthand"')
    shortcuts = android / "app/src/main/res/xml/shortcuts.xml"
    shortcuts_text = replace_once(shortcuts.read_text(encoding="utf-8"), 'android:targetPackage="org.b3log.siyuan"',
                                  'android:targetPackage="org.b3log.siyuan.fork"')

    # 包名、文件共享权限和快捷方式目标使用同一变体标识，Java 类仍使用原命名空间。
    root_gradle.write_text("\n".join(line for line in root_text.splitlines()
                                     if "maven.aliyun.com" not in line) + "\n", encoding="utf-8")
    app_gradle.write_text(app_text, encoding="utf-8")
    manifest.write_text(manifest_text, encoding="utf-8")
    shortcuts.write_text(shortcuts_text, encoding="utf-8")
    debug_shortcuts = android / "app/src/debug/res/xml/shortcuts.xml"
    debug_shortcuts.parent.mkdir(parents=True, exist_ok=True)
    debug_shortcuts.write_text(shortcuts_text.replace('android:targetPackage="org.b3log.siyuan.fork"',
                                                     'android:targetPackage="org.b3log.siyuan.fork.debug"'),
                               encoding="utf-8")

    # 密钥和密码只从构建环境读取，不写入源码或发布产物。
    (android / "signings.gradle").write_text('''android {
    signingConfigs {
        siyuanConfig {
            def keyPath = System.getenv("FORK_ANDROID_KEYSTORE_PATH")
            if (keyPath) {
                storeFile file(keyPath)
                storePassword System.getenv("FORK_ANDROID_KEYSTORE_PASSWORD")
                keyAlias System.getenv("FORK_ANDROID_KEY_ALIAS")
                keyPassword System.getenv("FORK_ANDROID_KEY_PASSWORD")
            }
        }
    }
    if (System.getenv("FORK_ANDROID_KEYSTORE_PATH")) {
        buildTypes {
            debug {
                signingConfig signingConfigs.siyuanConfig
            }
        }
    }
}
''', encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("android", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    prepare(args.repo, args.android)
