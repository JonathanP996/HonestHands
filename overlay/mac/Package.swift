// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "HHOverlay",
    platforms: [.macOS(.v14)],
    targets: [.executableTarget(name: "HHOverlay", path: "Sources/HHOverlay")]
)
