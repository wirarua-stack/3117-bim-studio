# SPDX-License-Identifier: GPL-3.0-or-later
"""Small FreeCAD-native dialogs; never installs Python or a second Qt runtime."""
import importlib.util
from pathlib import Path


def _support(root):
    path = root / "packaging" / "install_support.py"
    spec = importlib.util.spec_from_file_location("bim3117_install_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(root, mode="install"):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtWidgets

    root = Path(root)
    helper = _support(root)
    parent = Gui.getMainWindow()
    title = "3117 BIM Studio"
    user_data = Path(App.getUserAppDataDir())
    target = user_data / "Mod" / helper.INSTALL_NAME
    if App.listDocuments():
        QtWidgets.QMessageBox.information(parent, title,
            "กรุณาบันทึกและปิดเอกสารโมเดลทั้งหมดก่อนติดตั้งหรือจัดการรุ่น\n"
            "Please save and close all model documents, then execute this macro again.")
        return
    try:
        if mode == "install":
            info = helper.package_info(root)
            host = ".".join(str(part) for part in App.Version()[:3])
            text = (f"ติดตั้ง 3117 BIM Studio {info['version']} สำหรับบัญชีผู้ใช้นี้\n\n"
                    f"ตำแหน่ง: {target}\nFreeCAD ที่เปิด: {host}\n"
                    f"รุ่นเป้าหมาย: FreeCAD {helper.BASELINE}\n\n"
                    "รุ่นเดิมที่ติดตั้งด้วยตัวช่วยนี้จะเก็บสำรองไว้\n"
                    "หลังติดตั้งให้ปิด FreeCAD แล้วเปิดใหม่\n\nดำเนินการติดตั้งหรือไม่?")
            choice = QtWidgets.QMessageBox.question(parent, title, text,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if choice != QtWidgets.QMessageBox.Yes:
                return
            result = helper.install(root, user_data)
            outcome = "ติดตั้งไฟล์ workbench แล้ว / Workbench files installed."
        else:
            choices = ["ถอนการติดตั้งและเก็บสำรอง / Uninstall", "คืนรุ่นจากสำรอง / Restore backup"]
            action, accepted = QtWidgets.QInputDialog.getItem(parent, title, "เลือกการจัดการ", choices, 0, False)
            if not accepted:
                return
            if action == choices[0]:
                choice = QtWidgets.QMessageBox.question(parent, title,
                    f"ย้าย workbench นี้ออกจากรายการที่ FreeCAD โหลด และเก็บสำรองไว้?\n{target}\n\n"
                    "ไฟล์โครงการ .FCStd ของคุณไม่ถูกลบ",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
                if choice != QtWidgets.QMessageBox.Yes:
                    return
                result = helper.uninstall(user_data)
                outcome = "ถอน workbench ออกจากโฟลเดอร์ Mod แล้ว โดยเก็บไฟล์ไว้ในสำรอง"
            else:
                backups = helper.list_backups(user_data)
                if not backups:
                    QtWidgets.QMessageBox.information(parent, title, "ไม่พบรุ่นสำรองของ 3117 ในบัญชีผู้ใช้นี้")
                    return
                labels = [f"{item['name']} | v{item['version']}" for item in backups]
                label, accepted = QtWidgets.QInputDialog.getItem(parent, title,
                    "เลือกรุ่นสำรองที่จะคืน รุ่นปัจจุบันจะเก็บสำรองอีกชุด", labels, 0, False)
                if not accepted:
                    return
                result = helper.restore(user_data, backups[labels.index(label)]["name"])
                outcome = f"คืน workbench รุ่น {result['version']} แล้ว"
        backup_text = f"\nสำรอง: {result['backup']}" if result.get("backup") else ""
        App.Console.PrintMessage(outcome + "\n" + str(result) + "\n")
        QtWidgets.QMessageBox.information(parent, title,
            outcome + backup_text + "\n\nปิด FreeCAD ทุกหน้าต่าง แล้วเปิดใหม่\nRestart all FreeCAD windows.")
    except Exception as exc:
        App.Console.PrintError(f"3117 installer: {exc}\n")
        QtWidgets.QMessageBox.critical(parent, title,
            "ดำเนินการไม่สำเร็จ / Operation did not complete\n\n" + str(exc)
            + "\n\nดู Report view สำหรับรายละเอียด และอ่าน INSTALL_TH.md")
