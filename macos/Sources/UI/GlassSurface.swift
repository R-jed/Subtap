import AppKit
import SwiftUI

enum GlassSurfaceRole {
    case window
    case pane
    case card
    case control

    var material: NSVisualEffectView.Material {
        switch self {
        case .window:
            return .hudWindow
        case .pane:
            return .sidebar
        case .card, .control:
            return .popover
        }
    }

    var blendingMode: NSVisualEffectView.BlendingMode {
        self == .window ? .behindWindow : .withinWindow
    }

    var tint: Color {
        switch self {
        case .window:
            return SubtapTheme.background
        case .pane:
            return SubtapTheme.surface.opacity(0.62)
        case .card:
            return SubtapTheme.surface.opacity(0.72)
        case .control:
            return SubtapTheme.surface.opacity(0.50)
        }
    }

    var fallback: Color {
        switch self {
        case .window:
            return SubtapTheme.opaqueBackground
        case .pane, .card, .control:
            return SubtapTheme.surface
        }
    }
}

struct GlassSurfaceModifier: ViewModifier {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    let role: GlassSurfaceRole
    var cornerRadius: CGFloat
    var stroke: Bool

    func body(content: Content) -> some View {
        content
            .background(background)
            .overlay {
                if stroke {
                    shape.stroke(SubtapTheme.glassStroke, lineWidth: 1)
                }
            }
            .clipShape(shape)
    }

    @ViewBuilder
    private var background: some View {
        shape
            .fill(reduceTransparency ? role.fallback : role.tint)
            .background {
                if !reduceTransparency {
                    SubtapVisualEffectView(
                        material: role.material,
                        blendingMode: role.blendingMode,
                        state: .active
                    )
                    .clipShape(shape)
                }
            }
    }

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
    }
}

struct SubtapVisualEffectView: NSViewRepresentable {
    let material: NSVisualEffectView.Material
    let blendingMode: NSVisualEffectView.BlendingMode
    let state: NSVisualEffectView.State

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = blendingMode
        view.state = state
        view.isEmphasized = true
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = material
        view.blendingMode = blendingMode
        view.state = state
        view.isEmphasized = true
    }
}

extension View {
    func glassSurface(
        _ role: GlassSurfaceRole,
        cornerRadius: CGFloat = 0,
        stroke: Bool = false
    ) -> some View {
        modifier(GlassSurfaceModifier(role: role, cornerRadius: cornerRadius, stroke: stroke))
    }
}
