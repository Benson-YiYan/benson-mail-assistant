import AppKit

// Render at every native icon size so small Dock and Finder icons stay crisp.
let root = URL(fileURLWithPath: CommandLine.arguments[1])
let iconset = root.appendingPathComponent("MailIcon.iconset")
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)
func render(_ pixels: Int, to file: URL) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let context = NSGraphicsContext.current!.cgContext
    context.scaleBy(x: CGFloat(pixels) / 1024, y: CGFloat(pixels) / 1024)
    let tile = NSBezierPath(roundedRect: NSRect(x: 62, y: 62, width: 900, height: 900), xRadius: 204, yRadius: 204)
    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.22)
    shadow.shadowBlurRadius = 25
    shadow.shadowOffset = NSSize(width: 0, height: -12)
    shadow.set()
    NSColor.systemBlue.setFill()
    tile.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: NSColor(calibratedRed: 0.21, green: 0.66, blue: 1, alpha: 1),
               ending: NSColor(calibratedRed: 0.08, green: 0.26, blue: 0.83, alpha: 1))!.draw(in: tile, angle: -90)
    let envelope = NSBezierPath(roundedRect: NSRect(x: 218, y: 294, width: 588, height: 410), xRadius: 64, yRadius: 64)
    NSColor.white.setFill()
    envelope.fill()
    let folds = NSBezierPath()
    folds.move(to: NSPoint(x: 239, y: 322))
    folds.line(to: NSPoint(x: 435, y: 494))
    folds.move(to: NSPoint(x: 785, y: 322))
    folds.line(to: NSPoint(x: 589, y: 494))
    NSColor(calibratedRed: 0.79, green: 0.87, blue: 1, alpha: 1).setStroke()
    folds.lineWidth = 15
    folds.lineCapStyle = .round
    folds.stroke()
    let flap = NSBezierPath()
    flap.move(to: NSPoint(x: 239, y: 669))
    flap.line(to: NSPoint(x: 475, y: 487))
    flap.curve(to: NSPoint(x: 549, y: 487), controlPoint1: NSPoint(x: 498, y: 470), controlPoint2: NSPoint(x: 526, y: 470))
    flap.line(to: NSPoint(x: 785, y: 669))
    NSColor(calibratedRed: 0.16, green: 0.43, blue: 0.87, alpha: 1).setStroke()
    flap.lineWidth = 22
    flap.lineJoinStyle = .round
    flap.lineCapStyle = .round
    flap.stroke()
    let badge = NSBezierPath(ovalIn: NSRect(x: 689, y: 619, width: 174, height: 174))
    NSColor(calibratedRed: 1, green: 0.73, blue: 0.21, alpha: 1).setFill()
    badge.fill()
    let sparkle = NSBezierPath()
    sparkle.move(to: NSPoint(x: 776, y: 763))
    sparkle.line(to: NSPoint(x: 792, y: 722))
    sparkle.line(to: NSPoint(x: 833, y: 706))
    sparkle.line(to: NSPoint(x: 792, y: 690))
    sparkle.line(to: NSPoint(x: 776, y: 649))
    sparkle.line(to: NSPoint(x: 760, y: 690))
    sparkle.line(to: NSPoint(x: 719, y: 706))
    sparkle.line(to: NSPoint(x: 760, y: 722))
    sparkle.close()
    NSColor.white.setFill()
    sparkle.fill()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using: .png, properties: [:])!.write(to: file)
}
for size in [16, 32, 128, 256, 512] {
    try render(size, to: iconset.appendingPathComponent("icon_\(size)x\(size).png"))
    try render(size * 2, to: iconset.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
try render(1024, to: root.appendingPathComponent("MailIcon.png"))
