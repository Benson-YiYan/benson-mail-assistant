// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "BensonMailMac", platforms: [.macOS(.v14)], products: [.executable(name: "BensonMailMac", targets: ["BensonMailMac"])], targets: [.executableTarget(name: "BensonMailMac")])
