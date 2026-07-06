import SwiftUI

enum SubtapSettingsSection: CaseIterable, Identifiable {
    case appearance
    case timeline
    case transcription
    case export
    case advanced

    var id: Self { self }

    var title: String {
        switch self {
        case .appearance:
            return "外观"
        case .timeline:
            return "时间线"
        case .transcription:
            return "转录与模型"
        case .export:
            return "导出"
        case .advanced:
            return "高级"
        }
    }

    var systemImage: String {
        switch self {
        case .appearance:
            return "paintbrush"
        case .timeline:
            return "waveform"
        case .transcription:
            return "cpu"
        case .export:
            return "square.and.arrow.up"
        case .advanced:
            return "slider.horizontal.3"
        }
    }
}

struct SubtapSettingsView: View {
    @State private var selection: SubtapSettingsSection? = .appearance

    @AppStorage("settings.transparentWindow") private var transparentWindow = true
    @AppStorage("settings.sidebarGlass") private var sidebarGlass = true
    @AppStorage("settings.timelineFollowPlayback") private var timelineFollowPlayback = true
    @AppStorage("settings.spaceTogglesPlayback") private var spaceTogglesPlayback = true
    @AppStorage("settings.exportOverwriteWarning") private var exportOverwriteWarning = true

    var body: some View {
        NavigationSplitView {
            List(SubtapSettingsSection.allCases, selection: $selection) { section in
                Label(section.title, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationTitle("设置")
            .navigationSplitViewColumnWidth(min: 210, ideal: 220, max: 230)
        } detail: {
            ScrollView {
                settingsDetail(for: selection ?? .appearance)
                    .padding(24)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .frame(minWidth: 825, minHeight: 500)
        .glassSurface(.window)
    }

    @ViewBuilder
    private func settingsDetail(for section: SubtapSettingsSection) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Label(section.title, systemImage: section.systemImage)
                .font(.system(size: 20, weight: .bold))
                .foregroundStyle(SubtapTheme.text)

            switch section {
            case .appearance:
                settingsGroup {
                    Toggle("透明窗口", isOn: $transparentWindow)
                    Toggle("侧栏透明", isOn: $sidebarGlass)
                    Picker("玻璃强度", selection: .constant("标准")) {
                        Text("轻").tag("轻")
                        Text("标准").tag("标准")
                        Text("清透").tag("清透")
                    }
                    Picker("Accent", selection: .constant("紫蓝")) {
                        Text("系统").tag("系统")
                        Text("紫蓝").tag("紫蓝")
                        Text("跟随波形").tag("跟随波形")
                    }
                }
            case .timeline:
                settingsGroup {
                    Toggle("播放中自动跟随", isOn: $timelineFollowPlayback)
                    Toggle("空格播放/暂停", isOn: $spaceTogglesPlayback)
                    Picker("滚轮行为", selection: .constant("横向滚动")) {
                        Text("横向滚动").tag("横向滚动")
                        Text("缩放时间线").tag("缩放时间线")
                    }
                }
            case .transcription:
                settingsGroup {
                    LabeledContent("默认模型", value: "Qwen3-ASR-0.6B-4bit")
                    LabeledContent("模型目录", value: ModelManager.shared.modelsDirectory.path)
                    Toggle("转录前检查模型完整性", isOn: .constant(true))
                }
            case .export:
                settingsGroup {
                    Picker("默认格式", selection: .constant("SRT")) {
                        Text("SRT").tag("SRT")
                        Text("VTT").tag("VTT")
                    }
                    Toggle("覆盖前提醒", isOn: $exportOverwriteWarning)
                    Toggle("导出后在 Finder 中显示", isOn: .constant(false))
                }
            case .advanced:
                settingsGroup {
                    Toggle("详细日志", isOn: .constant(false))
                    Toggle("保留中间文件", isOn: .constant(true))
                    LabeledContent("当前版本", value: "Native Swift")
                }
            }
        }
        .frame(maxWidth: 520, alignment: .leading)
    }

    private func settingsGroup<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        Form {
            content()
        }
        .formStyle(.grouped)
        .scrollDisabled(true)
    }
}
