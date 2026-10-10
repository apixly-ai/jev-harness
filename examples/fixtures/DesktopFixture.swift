import Cocoa
class Controller: NSObject {
    var window: NSWindow?
    let name = NSTextField(string: "")
    let flexible = NSButton(checkboxWithTitle: "Flexible dates", target: nil, action: nil)
    let output = NSTextField(labelWithString: "No draft prepared")
    @objc func apply(_ sender: Any) {
        output.stringValue = "Draft ready: \(name.stringValue) | flexible=\(flexible.state == .on)"
    }
    func launch() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let win = NSWindow(contentRect: NSRect(x: 200,y: 200,width: 620,height: 350),styleMask: [.titled,.closable],backing: .buffered,defer: false)
        self.window = win
        win.title = "Jev Harness Desktop Fixture"
        let title = NSTextField(labelWithString: "Local travel draft — synthetic fixture")
        title.frame = NSRect(x:30,y:280,width:560,height:35)
        name.frame = NSRect(x:30,y:210,width:400,height:35)
        name.placeholderString = "Traveler name"
        name.setAccessibilityLabel("Traveler name")
        flexible.frame = NSRect(x:30,y:150,width:400,height:35)
        let button = NSButton(title: "Prepare draft", target: self, action: #selector(apply(_:)))
        button.frame = NSRect(x:30,y:95,width:200,height:40)
        output.frame = NSRect(x:30,y:30,width:560,height:40)
        for view in [title,name,flexible,button,output] as [NSView] {win.contentView!.addSubview(view)}
        win.setAccessibilityElement(true)
        win.setAccessibilityRole(.window)
        app.setAccessibilityWindows([win])
        win.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        app.run()
    }
}
let controller = Controller()
controller.launch()
