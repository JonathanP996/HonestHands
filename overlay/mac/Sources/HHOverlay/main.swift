// HonestHands native overlay (macOS). Speaks the JSON-lines protocol in ../../PROTOCOL.md.
import AppKit
import SwiftUI

// MARK: - Protocol

struct ShowCommand: Decodable {
    var cmd: String
    var id: String?
    var hard: Bool?
    var title: String?
    var context: String?
    var reason: String?
    var rule: String?
    var quote: String?
    var tip: String?
    var source: String?
    var allowSend: Bool?
    var allowLater: Bool?
    var choice: String?
}

func emit(_ obj: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: obj),
          let s = String(data: data, encoding: .utf8) else { return }
    print(s)
    fflush(stdout)
}

// MARK: - Model

final class OverlayModel: ObservableObject {
    @Published var visible = false
    @Published var cmd = ShowCommand(cmd: "show")
    @Published var pulse = 0          // bumps each show() to restart ripples
    @Published var checking = false
    @Published var okPill = false
    var onChoice: (String) -> Void = { _ in }
}

// MARK: - Views

struct Ripple: View {
    let color: Color
    let trigger: Int
    @State private var go = false
    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .stroke(color.opacity(go ? 0 : 0.55), lineWidth: 2)
                    .scaleEffect(go ? 2.6 : 0.9)
                    .animation(.easeOut(duration: 1.5).delay(Double(i) * 0.28).repeatCount(2, autoreverses: false), value: go)
            }
        }
        .onAppear { go = false; DispatchQueue.main.async { go = true } }
        .id(trigger)
    }
}

struct ActionButton: View {
    let title: String
    let hint: String?
    let style: Style
    let tint: Color
    let action: () -> Void
    enum Style { case primary, danger, secondary, quiet }
    @State private var hover = false
    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title).font(.system(size: 13, weight: .semibold))
                if let hint { Text(hint).font(.system(size: 11)).opacity(0.55) }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 9)
            .foregroundStyle(style == .primary ? Color.black.opacity(0.85) : style == .danger ? Color.white : Color.primary)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(style == .primary || style == .danger ? tint : Color.primary.opacity(hover ? 0.14 : (style == .secondary ? 0.08 : 0.0)))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .strokeBorder(Color.primary.opacity(style == .quiet ? 0.10 : 0), lineWidth: 1)
            )
            .scaleEffect(hover ? 1.02 : 1)
        }
        .buttonStyle(.plain)
        .onHover { h in
            withAnimation(.spring(response: 0.25, dampingFraction: 0.7)) { hover = h }
            if h { NSCursor.pointingHand.set() } else { NSCursor.arrow.set() }
        }
    }
}

struct CardView: View {
    @ObservedObject var m: OverlayModel
    @State private var expanded = false
    @State private var shown = [Bool](repeating: false, count: 7)

    var hard: Bool { m.cmd.hard ?? false }
    // The alert is red; only "Edit my message" is green.
    var accent: Color { Color(red: 0.90, green: 0.36, blue: 0.34) }
    var green: Color { Color(red: 0.42, green: 0.78, blue: 0.62) }

    func reveal(_ i: Int) -> some ViewModifier { Reveal(on: shown[i], delay: Double(i) * 0.05) }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            if m.checking && !m.visible {
                HStack(spacing: 9) {
                    ProgressView().controlSize(.small).scaleEffect(0.8)
                    Text("Checking with your professor…").font(.system(size: 12.5, weight: .medium))
                }
                .padding(.horizontal, 15).padding(.vertical, 10)
                .background(Capsule().fill(.ultraThinMaterial)
                    .overlay(Capsule().strokeBorder(Color.primary.opacity(0.12), lineWidth: 1))
                    .shadow(color: .black.opacity(0.3), radius: 14, y: 6))
                .padding(24)
                .transition(.move(edge: .trailing).combined(with: .opacity))
            }
            if m.okPill && !m.visible && !m.checking {
                HStack(spacing: 9) {
                    Image(systemName: "checkmark.circle.fill").font(.system(size: 15)).foregroundStyle(green)
                    Text("You’re good, sending it").font(.system(size: 12.5, weight: .medium))
                }
                .padding(.horizontal, 15).padding(.vertical, 10)
                .background(Capsule().fill(.ultraThinMaterial)
                    .overlay(Capsule().strokeBorder(green.opacity(0.5), lineWidth: 1))
                    .shadow(color: .black.opacity(0.3), radius: 14, y: 6))
                .padding(24)
                .transition(.move(edge: .trailing).combined(with: .opacity))
            }
            if m.visible {
                VStack(alignment: .leading, spacing: 0) {
                    // Header
                    HStack(spacing: 12) {
                        ZStack {
                            Ripple(color: accent, trigger: m.pulse).frame(width: 34, height: 34)
                            Circle().fill(accent.opacity(0.2)).frame(width: 34, height: 34)
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 15, weight: .bold)).foregroundStyle(accent)
                                .symbolEffect(.bounce, value: m.pulse)
                        }
                        VStack(alignment: .leading, spacing: 1) {
                            Text(m.cmd.title ?? "Hold on a second").font(.system(size: 16, weight: .semibold))
                            Text(m.cmd.context ?? "").font(.system(size: 11.5)).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer(minLength: 0)
                    }
                    .modifier(reveal(0))

                    if expanded {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(m.cmd.reason ?? "").font(.system(size: 13.5)).fixedSize(horizontal: false, vertical: true)
                                .modifier(reveal(1))
                            if let r = m.cmd.rule, !r.isEmpty {
                                (Text("Rule  ").foregroundStyle(.secondary).fontWeight(.semibold) + Text(r))
                                    .font(.system(size: 12.5)).fixedSize(horizontal: false, vertical: true)
                                    .modifier(reveal(2))
                            }
                            if let q = m.cmd.quote, !q.isEmpty {
                                HStack(spacing: 9) {
                                    Capsule().fill(accent.opacity(0.7)).frame(width: 3)
                                    Text("“\(q)”").font(.system(size: 12.5, design: .serif)).italic()
                                        .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                                }
                                .fixedSize(horizontal: false, vertical: true)
                                .modifier(reveal(3))
                            }
                            if let t = m.cmd.tip, !t.isEmpty {
                                HStack(alignment: .top, spacing: 7) {
                                    Image(systemName: "lightbulb.fill").font(.system(size: 11)).foregroundStyle(accent)
                                    Text(t).font(.system(size: 12.5)).foregroundStyle(accent)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                .modifier(reveal(4))
                            }
                            Text("Checked by the \(m.cmd.source ?? "guard")").font(.system(size: 10.5))
                                .foregroundStyle(.tertiary).modifier(reveal(5))

                            VStack(spacing: 8) {
                                HStack(spacing: 8) {
                                    ActionButton(title: hard ? "OK, I’ll edit it" : "Edit my message", hint: "↩",
                                                 style: .primary, tint: green) { m.onChoice("edit") }
                                    if m.cmd.allowSend ?? !hard {
                                        ActionButton(title: "Send it now", hint: "⌘↩", style: .danger, tint: accent) { m.onChoice("send_anyway") }
                                    }
                                }
                                if m.cmd.allowSend ?? !hard {
                                    HStack(spacing: 5) {
                                        Image(systemName: "doc.text.magnifyingglass").font(.system(size: 10))
                                        Text("Sending it now is recorded in your activity log.").font(.system(size: 11))
                                    }
                                    .foregroundStyle(.tertiary)
                                }
                            }
                            .modifier(reveal(6)).padding(.top, 4)
                        }
                        .padding(.top, 14)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                }
                .padding(18)
                .frame(width: 396)
                .background(
                    RoundedRectangle(cornerRadius: 24, style: .continuous).fill(.ultraThinMaterial)
                        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous)
                            .strokeBorder(LinearGradient(colors: [accent.opacity(0.55), Color.primary.opacity(0.08)],
                                                         startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1))
                        .shadow(color: .black.opacity(0.35), radius: 28, y: 14)
                )
                .padding(24)
                .transition(.move(edge: .trailing).combined(with: .opacity))
                .onAppear(perform: play)
                .onChange(of: m.pulse) { _ in play() }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
    }

    func play() {
        expanded = false
        shown = [Bool](repeating: false, count: shown.count)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.28) {
            withAnimation(.spring(response: 0.55, dampingFraction: 0.78)) { expanded = true }
            for i in shown.indices { shown[i] = true }
        }
    }
}

struct Reveal: ViewModifier {
    let on: Bool
    let delay: Double
    func body(content: Content) -> some View {
        content.opacity(on || delay == 0 ? 1 : 0).offset(y: on || delay == 0 ? 0 : 8)
            .animation(.easeOut(duration: 0.4).delay(delay), value: on)
    }
}

// MARK: - Window

final class FirstClickHost<V: View>: NSHostingView<V> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

final class OverlayPanel: NSPanel {
    var onKey: ((NSEvent) -> Bool)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func keyDown(with event: NSEvent) { if onKey?(event) != true { super.keyDown(with: event) } }
}

final class Controller {
    let model = OverlayModel()
    var panel: OverlayPanel!
    var currentId = ""
    var autoDismiss: Timer?
    var checkWork: DispatchWorkItem?

    func setup() {
        let size = NSSize(width: 460, height: 560)
        panel = OverlayPanel(contentRect: NSRect(origin: .zero, size: size),
                             styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.level = .statusBar
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.hidesOnDeactivate = false
        panel.isFloatingPanel = true
        panel.becomesKeyOnlyIfNeeded = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        let host = FirstClickHost(rootView: CardView(m: model))
        host.frame = NSRect(origin: .zero, size: size)
        panel.contentView = host
        model.onChoice = { [weak self] c in self?.choose(c) }
        panel.onKey = { [weak self] e in
            guard let self, self.model.visible else { return false }
            let chars = e.charactersIgnoringModifiers ?? ""
            if chars == "\u{1b}" || (chars == "\r" && !e.modifierFlags.contains(.command)) { self.choose("edit"); return true }
            if chars == "\r", e.modifierFlags.contains(.command), self.model.cmd.allowSend ?? !(self.model.cmd.hard ?? false) {
                self.choose("send_anyway"); return true
            }
            return false
        }
    }

    func place() {
        let s = (NSScreen.main ?? NSScreen.screens[0]).visibleFrame
        panel.setFrameOrigin(NSPoint(x: s.maxX - panel.frame.width, y: s.maxY - panel.frame.height))
    }

    func startChecking() {
        checkWork?.cancel()
        let w = DispatchWorkItem { [weak self] in          // only if it takes a moment: no flicker on instant results
            guard let self, !self.model.visible else { return }
            self.place(); self.panel.orderFrontRegardless()
            withAnimation(.spring(response: 0.4, dampingFraction: 0.85)) { self.model.checking = true }
        }
        checkWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35, execute: w)
    }

    func showOK() {
        checkWork?.cancel()
        guard model.checking, !model.visible else { return }     // instant results show nothing
        withAnimation(.spring(response: 0.4, dampingFraction: 0.85)) { model.checking = false; model.okPill = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { [weak self] in
            guard let self else { return }
            withAnimation(.easeIn(duration: 0.25)) { self.model.okPill = false }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                if !self.model.visible && !self.model.checking && !self.model.okPill { self.panel.orderOut(nil) }
            }
        }
    }

    func stopChecking() {
        checkWork?.cancel()
        withAnimation(.easeIn(duration: 0.2)) { model.checking = false }
    }

    func show(_ c: ShowCommand) {
        model.okPill = false
        stopChecking()
        currentId = c.id ?? ""
        model.cmd = c
        model.pulse += 1
        place()
        panel.orderFrontRegardless()
        withAnimation(.spring(response: 0.5, dampingFraction: 0.8)) { model.visible = true }
        autoDismiss?.invalidate()
        autoDismiss = Timer.scheduledTimer(withTimeInterval: 60, repeats: false) { [weak self] _ in self?.choose("edit") }
    }

    func choose(_ choice: String) {
        guard model.visible else { return }
        autoDismiss?.invalidate()
        emit(["event": "choice", "id": currentId, "choice": choice])
        dismiss()
    }

    func dismiss() {
        stopChecking()
        withAnimation(.easeIn(duration: 0.25)) { model.visible = false }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            if self?.model.visible == false && self?.model.checking == false && self?.model.okPill == false { self?.panel.orderOut(nil) }
        }
    }
}

// MARK: - Main

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let controller = Controller()
controller.setup()

DispatchQueue.global().async {
    while let line = readLine() {
        guard let data = line.data(using: .utf8),
              let cmd = try? JSONDecoder().decode(ShowCommand.self, from: data) else { continue }
        DispatchQueue.main.async {
            switch cmd.cmd {
            case "show": controller.show(cmd)
            case "checking": controller.startChecking()
            case "ok": controller.showOK()
            case "hide": controller.dismiss()
            case "choose":
                let c = cmd.choice ?? "edit"
                if c != "send_anyway" || (controller.model.cmd.allowSend ?? !(controller.model.cmd.hard ?? false)) { controller.choose(c) }
            case "quit": NSApp.terminate(nil)
            default: break
            }
        }
    }
    DispatchQueue.main.async { NSApp.terminate(nil) }  // parent closed our stdin
}
emit(["event": "ready"])
app.run()
