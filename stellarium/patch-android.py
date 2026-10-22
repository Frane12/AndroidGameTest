#!/usr/bin/env python3
"""Strict Android-only adaptations to pinned upstream Stellarium v26.3."""
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch-android.py /path/to/AndroidManifest.xml")
path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
replacements = {
    'package="org.stellarium.stellarium"': 'package="org.drnas.stellarium.port"',
    'android:label="Stellarium"': 'android:label="DRNAS Stellarium Native"',
}
for original, replacement in replacements.items():
    if source.count(original) != 1:
        raise SystemExit(f"Upstream Android manifest changed: {original}")
    source = source.replace(original, replacement)
# Avoid requesting unrestricted access to the entire device file system
# merely to display the first sky viewport. SAF import comes later.
source = source.replace(
    '    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />\n',
    "",
)
path.write_text(source, encoding="utf-8")
print("DRNAS Android package identifier, label, permissions: patched")


# JPL's binary ephemeris structs must stay byte-packed, but the pinned
# upstream header sets #pragma pack(1) *before* importing libc++ <cstdint>
# and <cstdio>. This contaminates standard type definitions and causes Qt's
# AlignedQArrayData to fail Clang's alignment checks on Android ARM64.
# Import standard headers at native alignment and scope pack(1) to structs.
jpl_header = path.parent.parent / "src/core/planetsephems/jpl_int.h"
jpl = jpl_header.read_text(encoding="utf-8")
old_jpl = "#pragma pack(1)\n\n#include <cstdint>\n#include <cstdio>"
new_jpl = "#include <cstdint>\n#include <cstdio>\n\n#pragma pack(push, 1)"
if jpl.count(old_jpl) != 1 or jpl.count("#pragma pack()") != 1:
    raise SystemExit("Pinned Stellarium JPL packing guard changed; refusing blind edit")
jpl = jpl.replace(old_jpl, new_jpl).replace("#pragma pack()", "#pragma pack(pop)")
jpl_header.write_text(jpl, encoding="utf-8")
print("Android JPL ephemeris: preserved packed structs, fixed libc++ header alignment")


# Remove upstream's obsolete Android all-files-access prompt from main.cpp.
# The Android manifest above deliberately drops MANAGE_EXTERNAL_STORAGE, and
# the first on-device sky viewport needs no unrestricted file-system access.
# This is the only usage of private Qt JNI headers in the pinned main.cpp.
# Qt's public application bootstrap remains unmodified.
main_path = path.parent.parent / "src/main.cpp"
main = main_path.read_text(encoding="utf-8")
private_includes = (
    "#ifdef Q_OS_ANDROID\n"
    "#include <QJniObject>\n"
    "#include <QJniEnvironment>\n"
    "#include <QtCore/private/qjnihelpers_p.h>\n"
    "#include <QtCore/private/qandroidextras_p.h>\n"
    "#endif\n"
)
if main.count(private_includes) != 1:
    raise SystemExit("Pinned Stellarium Qt JNI imports changed; refusing blind edit")
main = main.replace(private_includes, "", 1)
block_start = '\n#ifdef Q_OS_ANDROID\n\tif (!QJniObject::callStaticMethod<jboolean>("android/os/Environment", "isExternalStorageManager"))'
block_end = "\n#endif\n\n\t// Init the file manager"
if main.count(block_start) != 1 or main.count(block_end) != 1:
    raise SystemExit("Pinned Stellarium Android storage prompt changed; refusing blind edit")
start = main.index(block_start)
end = main.index(block_end, start)
main = main[:start] + main[end + len("\n#endif"):]
main_path.write_text(main, encoding="utf-8")
print("Android main.cpp: dropped unused Qt private JNI headers and obsolete all-files permission prompt")

# Android needs app-private storage for its writable configuration, not
# ~/.stellarium if QDir::homePath() resolves outside the app sandbox.
anchor = '\t// Init the file manager\n\tStelFileMgr::init();'
replacement = (
    '#ifdef Q_OS_ANDROID\n'
    '\tconst QString drnasUserDir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);\n'
    '\tif (drnasUserDir.isEmpty())\n'
    '\t\tqFatal("DRNAS Android: app-private data directory unavailable");\n'
    '\tqputenv("STEL_USERDIR", drnasUserDir.toUtf8());\n'
    '\tqInfo().noquote() << "DRNAS Android user data:" << drnasUserDir;\n'
    '#endif\n\n'
    '\t// Init the file manager\n'
    '\tStelFileMgr::init();'
)
if main.count(anchor) != 1:
    raise SystemExit("Pinned Stellarium file-manager init changed; refusing blind patch")
main = main.replace(anchor, replacement, 1)
include_anchor = '#include <QDir>\n#include <QFile>'
if main.count(include_anchor) != 1:
    raise SystemExit("Pinned Stellarium Qt includes changed")
main = main.replace(include_anchor, '#include <QDir>\n#include <QStandardPaths>\n#include <QFile>', 1)
main_path.write_text(main, encoding="utf-8")
print("Android main.cpp: use private writable app data directory for Stellarium configuration")


# Android's desktop Qt dialogs live inside QGraphicsProxyWidget overlays.
# Desktop-saved geometry may exceed the phone screen, and the upstream
# inactive-window transparency makes the star field show through controls.
# Adapt only the pinned Android build, leaving desktop Stellarium unchanged.
dialog_cpp_path = path.parent.parent / "src/gui/StelDialog.cpp"
dialog_hpp_path = path.parent.parent / "src/gui/StelDialog.hpp"
dialog_cpp = dialog_cpp_path.read_text(encoding="utf-8")
dialog_hpp = dialog_hpp_path.read_text(encoding="utf-8")


def replace_unique(content, needle, replacement, label):
    if content.count(needle) != 1:
        raise SystemExit(f"Stellarium 26.3 GUI source changed ({label}); refusing blind edit")
    return content.replace(needle, replacement, 1)


dialog_helpers = r"""
#ifdef Q_OS_ANDROID
// Qt Widgets dialogs are rendered as graphics items on Android.
// Use logical view pixels (not physical display pixels); scaling the proxy
// also scales hit testing, so touch coordinates continue to match controls.
static void drnasFitAndroidDialog(CustomProxy* proxy, QWidget* widget)
{
    if (!proxy || !widget)
        return;

    const QSizeF viewSize(StelMainView::getInstance().size());
    if (viewSize.width() <= 0.0 || viewSize.height() <= 0.0)
        return;

    constexpr qreal margin = 12.0;
    const qreal maxWidth = qMax(qreal(1), viewSize.width() - 2.0 * margin);
    const qreal maxHeight = qMax(qreal(1), viewSize.height() - 2.0 * margin);
    const QSizeF originalSize = proxy->size();
    const qreal contentWidth = qMax(qreal(1), originalSize.width());
    const qreal contentHeight = qMax(qreal(1), originalSize.height());
    const qreal fit = qMin(qreal(1), qMin(maxWidth / contentWidth,
                                        maxHeight / contentHeight));

    // Always recompute from unscaled layout dimensions: never accumulate
    // scaling across reopening, device rotation or font-size changes.
    proxy->setTransformOriginPoint(QPointF(0, 0));
    proxy->setScale(fit);
    proxy->setPos(qMax(qreal(0), (viewSize.width() - contentWidth * fit) / 2.0),
                  qMax(qreal(0), (viewSize.height() - contentHeight * fit) / 2.0));
    widget->setWindowOpacity(1.0);
}
#endif

"""
dialog_cpp = replace_unique(
    dialog_cpp,
    "#include <QMessageBox>\n\nStelDialog::StelDialog",
    "#include <QMessageBox>\n\n" + dialog_helpers + "StelDialog::StelDialog",
    "Android dialog helper",
)

dialog_cpp = replace_unique(
    dialog_cpp,
    "\tconnect(&StelApp::getInstance(), &StelApp::colorSchemeChanged, this, &StelDialog::handleColorSchemeChanged);",
    "\tconnect(&StelApp::getInstance(), &StelApp::colorSchemeChanged, this, &StelDialog::handleColorSchemeChanged);"
    "\n#ifdef Q_OS_ANDROID\n"
    "\tconnect(&StelMainView::getInstance(), &StelMainView::sizeChanged, this,\n"
    "\t        [this](const QSize&) {\n"
    "\t            if (dialog && proxy && dialog->isVisible())\n"
    "\t                drnasFitAndroidDialog(proxy, dialog);\n"
    "\t        });\n"
    "#endif",
    "rotation / resize callback",
)

dialog_cpp = replace_unique(
    dialog_cpp,
    "\t\t\tconnect(proxy, &CustomProxy::sizeChanged, this, &StelDialog::handleDialogSizeChanged);",
    "\t\t\tconnect(proxy, &CustomProxy::sizeChanged, this, &StelDialog::handleDialogSizeChanged);"
    "\n#ifdef Q_OS_ANDROID\n"
    "\t\t\tconnect(proxy, &CustomProxy::sizeChanged, this, [this](QSizeF) {\n"
    "\t\t\t\tif (dialog && dialog->isVisible())\n"
    "\t\t\t\t\tdrnasFitAndroidDialog(proxy, dialog);\n"
    "\t\t\t});\n"
    "#endif",
    "dynamic dialog resize",
)

# The desktop code restores sometimes huge old window sizes and then clips
# them to 95% of the phone, hiding child widgets. Keep natural layout size
# on Android and scale its graphics proxy instead.
dialog_cpp = replace_unique(
    dialog_cpp,
    "\t\t\tif(proxy->size().width() > maxSize.width() || proxy->size().height() > maxSize.height())",
    "#ifndef Q_OS_ANDROID\n"
    "\t\t\tif(proxy->size().width() > maxSize.width() || proxy->size().height() > maxSize.height())",
    "native size clamp guard",
)
dialog_cpp = replace_unique(
    dialog_cpp,
    "\t\t\thandleDialogSizeChanged(proxy->size()); // This may trigger internal updates in subclasses. E.g. LocationPanel location arrow.",
    "#endif\n"
    "\t\t\thandleDialogSizeChanged(proxy->size()); // This may trigger internal updates in subclasses. E.g. LocationPanel location arrow.",
    "native size clamp end",
)
dialog_cpp = replace_unique(
    dialog_cpp,
    "\t\tproxy->setFocus();",
    "#ifdef Q_OS_ANDROID\n"
    "\t\t// Keep every dialog inside the current viewport, also on reopen.\n"
    "\t\tdrnasFitAndroidDialog(proxy, dialog);\n"
    "#endif\n"
    "\t\tproxy->setFocus();",
    "fit on every show",
)
dialog_cpp = replace_unique(
    dialog_cpp,
    "\t\t\tdialog = new QDialog(nullptr);",
    "\t\t\tdialog = new QDialog(nullptr);"
    "\n#ifdef Q_OS_ANDROID\n"
    "\t\t\t// Paint the window background fully instead of exposing the sky.\n"
    "\t\t\tdialog->setAutoFillBackground(true);\n"
    "\t\t\tdialog->setWindowOpacity(1.0);\n"
    "#endif",
    "opaque Android window",
)
dialog_hpp = replace_unique(
    dialog_hpp,
    '\t\t\tif (StelApp::getInstance().getSettings()->value("gui/flag_use_window_transparency", true).toBool())',
    '#ifndef Q_OS_ANDROID\n'
    '\t\t\tif (StelApp::getInstance().getSettings()->value("gui/flag_use_window_transparency", true).toBool())',
    "disable inactive Android window transparency",
)
dialog_hpp = replace_unique(
    dialog_hpp,
    "\t\t\treturn QGraphicsProxyWidget::event(event);",
    "#endif\n\t\t\treturn QGraphicsProxyWidget::event(event);",
    "Android transparency guard end",
)
dialog_cpp_path.write_text(dialog_cpp, encoding="utf-8")
dialog_hpp_path.write_text(dialog_hpp, encoding="utf-8")
print("Android Qt dialogs: scale to portrait/landscape viewport, recenter on reopen/rotate, preserve opaque controls")


# Android refinement: keep star/planet information inside a usable corner
# instead of letting the long desktop HTML text cover the whole sky scene.
# Default to ShortInfo on mobile, but honor explicit "all"/"custom" choices.
sky_cpp_path = path.parent.parent / "src/gui/SkyGui.cpp"
sky_cpp = sky_cpp_path.read_text(encoding="utf-8")
sky_helper = r"""
#ifdef Q_OS_ANDROID
// Fit existing rich-text content without changing the selected object,
// its data, the general GUI DPI, or Qt's touch-coordinate mapping.
static void drnasFitAndroidObjectInfo(QGraphicsTextItem* panel)
{
    if (!panel)
        return;
    const QSize viewport = StelMainView::getInstance().size();
    if (viewport.width() <= 0 || viewport.height() <= 0)
        return;
    const QRectF textRect = panel->boundingRect();
    if (textRect.width() <= 0 || textRect.height() <= 0)
        return;

    const bool portrait = viewport.height() > viewport.width();
    const qreal widthBudget = viewport.width() * (portrait ? 0.70 : 0.32);
    const qreal heightBudget = viewport.height() * 0.72;
    const qreal fit = qMin(qreal(1.0), qMin(widthBudget / textRect.width(),
                                           heightBudget / textRect.height()));
    panel->setTransformOriginPoint(QPointF(0, 0));
    panel->setScale(fit);
}
#endif

"""
sky_cpp = replace_unique(
    sky_cpp,
    "#include <QGraphicsDropShadowEffect>\n\nInfoPanel::InfoPanel",
    "#include <QGraphicsDropShadowEffect>\n\n" + sky_helper + "InfoPanel::InfoPanel",
    "star info adaptive helper",
)
sky_cpp = replace_unique(
    sky_cpp,
    '\tQString objectInfo = conf->value("gui/selected_object_info", "default").toString();',
    '\tQString objectInfo = conf->value("gui/selected_object_info", "default").toString();\n'
    '#ifdef Q_OS_ANDROID\n'
    '\tif (objectInfo == "default") objectInfo = "short";\n'
    '#endif',
    "compact Android default star info",
)
sky_cpp = replace_unique(
    sky_cpp,
    '\t\t\t+ "</span></div>");',
    '\t\t\t+ "</span></div>");\n'
    '#ifdef Q_OS_ANDROID\n'
    '\t\tdrnasFitAndroidObjectInfo(this);\n'
    '#endif',
    "star info reflow",
)
sky_cpp = replace_unique(
    sky_cpp,
    '\tQGraphicsWidget::resizeEvent(event);\n\tupdateBarsPos();',
    '\tQGraphicsWidget::resizeEvent(event);\n\tupdateBarsPos();\n'
    '#ifdef Q_OS_ANDROID\n'
    '\tdrnasFitAndroidObjectInfo(infoPanel);\n'
    '#endif',
    "star info rotation handling",
)
sky_cpp_path.write_text(sky_cpp, encoding="utf-8")
print("Android sky info: responsive bounds and compact default (user overrides retained)")

# Hide the non-modal Oculars control overlay while its full configuration
# dialog is open. Leaving both onscreen creates duplicated, overlapping
# controls at the top edge on a phone. Restore the overlay on close, only
# if the user enabled it; telescope/CCD data and plugin actions are intact.
ocular_cpp_path = path.parent.parent / "plugins/Oculars/src/Oculars.cpp"
ocular_cpp = ocular_cpp_path.read_text(encoding="utf-8")
ocular_cpp = replace_unique(
    ocular_cpp,
    '\t\tocularDialog = new OcularDialog(this, &ccds, &oculars, &telescopes, &lenses);',
    '\t\tocularDialog = new OcularDialog(this, &ccds, &oculars, &telescopes, &lenses);\n'
    '#ifdef Q_OS_ANDROID\n'
    '\t\tconnect(ocularDialog, &StelDialog::visibleChanged, this, [this](bool shown) {\n'
    '\t\t\tif (guiPanel)\n'
    '\t\t\t\tguiPanel->setVisible(!shown && flagGuiPanelEnabled);\n'
    '\t\t});\n'
    '#endif',
    "Oculars Android settings overlay",
)
ocular_cpp_path.write_text(ocular_cpp, encoding="utf-8")
print("Android Oculars: hide duplicate toolbar while settings dialog is open")


# Android visual modes and DPR diagnostics. Preserve existing config files and
# make the preset switchable from the real Stellarium sky-view options window.
# The Qt 6.8 OpenGL framebuffer follows logical viewport * devicePixelRatio;
# do not force desktop 1024x768, disable native DPI, or upsample an FBO.
main_path = path.parent.parent / "src/main.cpp"
main = main_path.read_text(encoding="utf-8")
main = replace_unique(
    main,
    '\tQ_ASSERT(confSettings);\n\tqInfo().noquote() << "Config file:"',
    '\tQ_ASSERT(confSettings);\n'
    '#ifdef Q_OS_ANDROID\n'
    '\t// One-time mobile visual preset migration; never reset user choices on next boot.\n'
    '\tif (!confSettings->contains("drnas/enhanced_sky"))\n'
    '\t{\n'
    '\t\tconfSettings->setValue("drnas/enhanced_sky", true);\n'
    '\t\tconfSettings->setValue("stars/relative_scale", 1.18);\n'
    '\t\tconfSettings->setValue("stars/absolute_scale", 1.10);\n'
    '\t\tconfSettings->setValue("landscape/flag_minimal_brightness", true);\n'
    '\t\tconfSettings->setValue("landscape/minimal_brightness", 0.10);\n'
    '\t\tconfSettings->sync();\n'
    '\t\tqInfo() << "DRNAS Android: Enhanced sky initial preset";\n'
    '\t}\n'
    '#endif\n'
    '\tqInfo().noquote() << "Config file:"',
    "Android default visual profile",
)
main_path.write_text(main, encoding="utf-8")

view_path = path.parent.parent / "src/gui/ViewDialog.cpp"
view = view_path.read_text(encoding="utf-8")
view = replace_unique(
    view,
    '#include "StelCore.hpp"\n#include "StelModule.hpp"',
    '#include "StelCore.hpp"\n#include "StelSkyDrawer.hpp"\n#include "StelModule.hpp"',
    "Android visual preset sky drawer include",
)
view = replace_unique(
    view,
    '#include <QSignalBlocker>\n#include <QTimer>',
    '#include <QSignalBlocker>\n#include <QCheckBox>\n#include <QLayout>\n#include <QTimer>',
    "Android visual preset UI includes",
)
view = replace_unique(
    view,
    '\tLandscapeMgr* lmgr = GETSTELMODULE(LandscapeMgr);\n\tQ_ASSERT(lmgr);',
    '\tLandscapeMgr* lmgr = GETSTELMODULE(LandscapeMgr);\n\tQ_ASSERT(lmgr);\n'
    '#ifdef Q_OS_ANDROID\n'
    '\t// Mobile-only switch in the original Sky and Viewing Options dialog.\n'
    '\t// Keep the real astronomical tone mapping and GL renderer untouched.\n'
    '\tQCheckBox* enhanced = new QCheckBox(tr("DRNAS Enhanced sky (turn off for Realistic)"), ui->starGroupBox);\n'
    '\tenhanced->setToolTip(tr("Enhanced: slightly brighter stars and landscape. Realistic: original Stellarium sky brightness."));\n'
    '\tif (ui->starGroupBox->layout())\n'
    '\t\tui->starGroupBox->layout()->addWidget(enhanced);\n'
    '\tenhanced->setChecked(app->getSettings()->value("drnas/enhanced_sky", true).toBool());\n'
    '\tconnect(enhanced, &QCheckBox::toggled, this, [app, lmgr](bool useEnhanced) {\n'
    '\t\tStelSkyDrawer* drawer = app->getCore()->getSkyDrawer();\n'
    '\t\tdrawer->setRelativeStarScale(useEnhanced ? 1.18 : 1.0);\n'
    '\t\tdrawer->setAbsoluteStarScale(useEnhanced ? 1.10 : 1.0);\n'
    '\t\tlmgr->setFlagLandscapeUseMinimalBrightness(useEnhanced);\n'
    '\t\tapp->getSettings()->setValue("drnas/enhanced_sky", useEnhanced);\n'
    '\t\tapp->getSettings()->sync();\n'
    '\t});\n'
    '#endif',
    "Android visual modes checkbox",
)
view_path.write_text(view, encoding="utf-8")

main_view_path = path.parent.parent / "src/StelMainView.cpp"
main_view = main_view_path.read_text(encoding="utf-8")
main_view = replace_unique(
    main_view,
    '\t\tconst QSize& sz = event->size();\n\t\tscene()->setSceneRect(QRect(QPoint(0, 0), sz));',
    '\t\tconst QSize& sz = event->size();\n'
    '#ifdef Q_OS_ANDROID\n'
    '\t\t// Qt OpenGL framebuffer target is logical widget size multiplied by\n'
    '\t\t// devicePixelRatioF(). Diagnostic only: never artificially downscale.\n'
    '\t\tconst qreal dpr = devicePixelRatioF();\n'
    '\t\tqInfo().nospace() << "DRNAS Android viewport: logical=" << sz.width() << "x" << sz.height()\n'
    '\t\t                  << " DPR=" << dpr << " expected physical framebuffer="\n'
    '\t\t                  << qRound(sz.width() * dpr) << "x" << qRound(sz.height() * dpr);\n'
    '#endif\n'
    '\t\tscene()->setSceneRect(QRect(QPoint(0, 0), sz));',
    "Android DPI framebuffer diagnostics",
)
main_view_path.write_text(main_view, encoding="utf-8")
print("Android visual modes: Enhanced/Realistic toggle, mobile contrast defaults, DPR-aware render diagnostics")


# DRNAS Android rotation-safe splash / fullscreen layout.
# On Qt Android QSplashScreen is hosted by the Activity surface, not a
# desktop-sized native popup. Painting a fixed desktop pixmap leaves most of
# the activity gray and clips the image when it rotates. Render the complete
# Android splash against the CURRENT widget size each paint instead.
splash_path = path.parent.parent / "src/StelSplashScreen.cpp"
splash = splash_path.read_text(encoding="utf-8")
splash = replace_unique(
    splash,
    "\tinstance->show();\n\n#if !defined(Q_OS_ANDROID)",
    "#ifdef Q_OS_ANDROID\n"
    "\t// Android's Activity window is fullscreen; let Qt resize it on rotation.\n"
    "\tinstance->showFullScreen();\n"
    "#else\n"
    "\tinstance->show();\n"
    "#endif\n\n#if !defined(Q_OS_ANDROID)",
    "Android fullscreen splash",
)
splash = replace_unique(
    splash,
    "\tsetPixmap(makePixmap(sizeRatio));",
    "#ifdef Q_OS_ANDROID\n"
    "\t// QSplashScreen uses pixmap size as its desktop window size. Android\n"
    "\t// paints the actual responsive splash in paintEvent below instead.\n"
    "\tsetPixmap(QPixmap(1, 1));\n"
    "\tsetAutoFillBackground(false);\n"
    "#else\n"
    "\tsetPixmap(makePixmap(sizeRatio));\n"
    "#endif",
    "Android splash pixmap preferred size",
)
android_splash_paint = r"""
#ifdef Q_OS_ANDROID
    Q_UNUSED(event)
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::SmoothPixmapTransform, true);

    // Never expose Android's default gray Activity background.
    p.fillRect(rect(), QColor(5, 9, 17));

    if (width() > 0 && height() > 0)
    {
        QFont heading = titleFont;
        heading.setPixelSize(qBound(19, height() / 11, 44));
        p.setFont(heading);
        p.setPen(Qt::white);
        const int header = qBound(34, height() / 8, 62);
        p.drawText(QRect(12, 6, qMax(1, width() - 24), header),
                   Qt::AlignCenter, titleText);

        // Calculate geometry on EVERY repaint: after portrait/landscape
        // changes the image remains centered, uncropped, and aspect-correct.
        QPixmap original(StelFileMgr::findFile("data/splash.png"));
        const QRect imageArea = rect().adjusted(16, header + 12, -16, -62);
        if (!original.isNull() && imageArea.width() > 0 && imageArea.height() > 0)
        {
            const QSize fitted = original.size().scaled(imageArea.size(),
                                                        Qt::KeepAspectRatio);
            const QPoint topLeft(imageArea.x() + (imageArea.width() - fitted.width()) / 2,
                                 imageArea.y() + (imageArea.height() - fitted.height()) / 2);
            p.drawPixmap(QRect(topLeft, fitted), original);
        }

        QFont version = splashFont;
        version.setPixelSize(qBound(11, height() / 31, 19));
        p.setFont(version);
        p.drawText(QRect(16, height() - 58, qMax(1, width() - 32), 24),
                   Qt::AlignHCenter | Qt::AlignVCenter,
                   StelUtils::getApplicationPublicVersion());
    }

    // Preserve the upstream live loading message.
    QSplashScreen::drawContents(&p);
    painted = true;
    return;
#else
"""
splash = replace_unique(
    splash,
    "\tQSplashScreen::paintEvent(event);\n\n\tQPainter p(this);",
    android_splash_paint + "\tQSplashScreen::paintEvent(event);\n\n\tQPainter p(this);",
    "Android splash adaptive painting",
)
splash = replace_unique(
    splash,
    "\tpainted=true;\n}\n\nQPixmap SplashScreen::SplashScreenWidget::makePixmap",
    "\tpainted=true;\n#endif\n}\n\nQPixmap SplashScreen::SplashScreenWidget::makePixmap",
    "Android splash paint guard end",
)
splash_path.write_text(splash, encoding="utf-8")
print("DRNAS Android splash: fullscreen, opaque, responsive image with aspect ratio on rotation")

# The desktop startup applies a stale 1024x768 config window size and may
# intersect the native rectangle with a geometry sampled BEFORE the screen
# finishes rotating during startup. Android's Qt Activity owns this size;
# don't override it with desktop geometry.
main = main_path.read_text(encoding="utf-8")
main = replace_unique(
    main,
    "\tmainWin.resize(size);",
    "#ifndef Q_OS_ANDROID\n"
    "\tmainWin.resize(size);\n"
    "#endif",
    "Android bypass desktop 1024x768 resize",
)
main = replace_unique(
    main,
    '\tconst bool fullscreen = confSettings->value("video/fullscreen", true).toBool();',
    "#ifdef Q_OS_ANDROID\n"
    "\t// Let the Android Activity resize the native surface on orientation\n"
    "\t// changes; avoid desktop geometry sampled before rotation completed.\n"
    "\tmainWin.setFullScreen(true);\n"
    "#else\n"
    '\tconst bool fullscreen = confSettings->value("video/fullscreen", true).toBool();',
    "Android Activity fullscreen",
)
main = replace_unique(
    main,
    "\n\tmainWin.show();",
    "\n#endif\n\n\tmainWin.show();",
    "Android Activity fullscreen guard end",
)
main_path.write_text(main, encoding="utf-8")
print("DRNAS Android main window: rely on current Activity viewport, not persisted desktop geometry")


# Android rotation splash repair: the upstream splash is a standalone
# QSplashScreen whose original pixmap size never follows a device rotation.
# Refit the pixmap whenever the splash window receives a resize event.
splash_hpp_path = path.parent.parent / "src/StelSplashScreen.hpp"
splash_cpp_path = path.parent.parent / "src/StelSplashScreen.cpp"
splash_hpp = splash_hpp_path.read_text(encoding="utf-8")
splash_cpp = splash_cpp_path.read_text(encoding="utf-8")
splash_hpp = replace_unique(
    splash_hpp,
    '\t\tvoid paintEvent(QPaintEvent*) override;',
    '\t\tvoid paintEvent(QPaintEvent*) override;\n'
    '#ifdef Q_OS_ANDROID\n'
    '\t\tvoid resizeEvent(QResizeEvent*) override;\n'
    '#endif',
    "Android splash resize declaration",
)
splash_cpp = replace_unique(
    splash_cpp,
    '\tsetPixmap(makePixmap(sizeRatio));',
    '#ifdef Q_OS_ANDROID\n'
    '\t// Keep the splash inside the screen, including narrow portrait displays.\n'
    '\tconst QSize available = QGuiApplication::primaryScreen()->availableGeometry().size();\n'
    '\tQPixmap image = makePixmap(sizeRatio);\n'
    '\tif (!available.isEmpty())\n'
    '\t\timage = image.scaled(available * 0.90, Qt::KeepAspectRatio, Qt::SmoothTransformation);\n'
    '\tsetPixmap(image);\n'
    '#else\n'
    '\tsetPixmap(makePixmap(sizeRatio));\n'
    '#endif',
    "Android splash fit initial screen",
)
splash_cpp = replace_unique(
    splash_cpp,
    'void SplashScreen::SplashScreenWidget::paintEvent(QPaintEvent* event)',
    '#ifdef Q_OS_ANDROID\n'
    'void SplashScreen::SplashScreenWidget::resizeEvent(QResizeEvent* event)\n'
    '{\n'
    '\tQSplashScreen::resizeEvent(event);\n'
    '\t// Do not force the original desktop-sized image after rotation.\n'
    '\tupdate();\n'
    '}\n'
    '#endif\n\n'
    'void SplashScreen::SplashScreenWidget::paintEvent(QPaintEvent* event)',
    "Android splash resize handler",
)
splash_hpp_path.write_text(splash_hpp, encoding="utf-8")
splash_cpp_path.write_text(splash_cpp, encoding="utf-8")
print("Android splash: limit image to available screen and refresh after rotation")
