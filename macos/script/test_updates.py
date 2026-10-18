"""Compile the actual native update client against offline HTTPS response fixtures."""
import json
from pathlib import Path
import subprocess
import tempfile

project = Path(__file__).resolve().parents[1]
source = r'''
import AppKit
import SwiftUI
final class AppLanguage: ObservableObject { static let shared = AppLanguage(); var code = "zh" }
func T(_ value: String) -> String { value }
@MainActor final class MailStore {
 static let shared = MailStore()
 struct Settings { var enabled = true }
 var settings = Settings(); var updating = false
 let base = URL(fileURLWithPath:"/tmp/benson-updater-fixture")
 var data: URL { base }
 func save() throws {}; func startWorker() {}
 func pauseForUpdate() throws -> Bool {let old=settings.enabled;settings.enabled=false;return old}
 func restoreAfterUpdate(_ value:Bool) throws {settings.enabled=value}
}
enum ServiceInstaller {
 static var worker: URL { URL(fileURLWithPath:"/usr/bin/false") }
 static func stop() throws {}
}
final class DownloadFixture: URLProtocol {
 override class func canInit(with request:URLRequest)->Bool { request.url?.host == "updates.example.invalid" }
 override class func canonicalRequest(for request:URLRequest)->URLRequest { request }
 override func startLoading() {
  let status = request.url!.path == "/http" ? 503 : 200
  let response = HTTPURLResponse(url:request.url!,statusCode:status,httpVersion:"HTTP/1.1",headerFields:["Content-Length":"3"])!
  client?.urlProtocol(self,didReceive:response,cacheStoragePolicy:.notAllowed)
  if request.url!.path == "/cancel" { return }
  client?.urlProtocol(self,didLoad:Data("abc".utf8))
  client?.urlProtocolDidFinishLoading(self)
 }
 override func stopLoading() {}
}
@main struct Fixtures {
 @MainActor static func main() async throws {
  let suite = "BensonMail.UpdateFixture." + UUID().uuidString
  let defaults = UserDefaults(suiteName: suite)!
  defer { defaults.removePersistentDomain(forName: suite) }
  let endpoint = URL(string:"https://updates.example.invalid/mail.json")!
  func manifest(_ version: String, link: String = "https://updates.example.invalid/app.dmg") throws -> Data {
   try JSONSerialization.data(withJSONObject:["schema_version":1,"platforms":[AppUpdater.platform:["version":version,"url":link,"sha256":String(repeating:"a",count:64),"notes":"Fixture release"]]])
  }
  let current = "202610180900"
  var calls = 0
  let newer = try manifest("202610180901")
  let client = AppUpdater(defaults: defaults,currentVersion:current,endpoint:{endpoint},fetch:{ request in
   calls += 1
   precondition(request.timeoutInterval == 25 && request.url == endpoint)
   return (newer,HTTPURLResponse(url:endpoint,statusCode:200,httpVersion:nil,headerFields:nil)!)
  })
  precondition(client.isDue())
  await client.check(manual:false)
  precondition(calls == 1 && client.available?.version == "202610180901" && !client.isDue())
  await client.check(manual:false)
  precondition(calls == 1)
  let restarted = AppUpdater(defaults:defaults,currentVersion:current)
  precondition(!restarted.isDue() && restarted.isDue(at:Date().addingTimeInterval(5*3600+1)))
  await client.check(manual:true)
  precondition(calls == 2)
  let equal = try manifest(current)
  let equalResult = try AppUpdater.parse(equal,platform:AppUpdater.platform,current:current)
  precondition(equalResult == nil)
  for link in ["http://updates.example.invalid/a.dmg","https://user:secret@updates.example.invalid/a.dmg"] {
   let bad = try manifest("202610180901",link:link)
   do { _ = try AppUpdater.parse(bad,platform:AppUpdater.platform,current:current); fatalError("insecure download accepted") } catch {}
  }
  for replacement in ["bad-hash", ""] {
   var malformed = try JSONSerialization.jsonObject(with:newer) as! [String:Any]
   var platforms = malformed["platforms"] as! [String:[String:Any]]
   platforms[AppUpdater.platform]!["sha256"] = replacement
   malformed["platforms"] = platforms
   let bad = try JSONSerialization.data(withJSONObject:malformed)
   do { _ = try AppUpdater.parse(bad,platform:AppUpdater.platform,current:current); fatalError("invalid hash accepted") } catch {}
  }
  var bilingual = try JSONSerialization.jsonObject(with:newer) as! [String:Any]
  var bilingualPlatforms = bilingual["platforms"] as! [String:[String:Any]]
  bilingualPlatforms[AppUpdater.platform]!["notes"] = ["zh":"中文更新", "en":"English update"]
  bilingual["platforms"] = bilingualPlatforms
  let bilingualResult = try AppUpdater.parse(JSONSerialization.data(withJSONObject:bilingual),platform:AppUpdater.platform,current:current)!
  precondition(bilingualResult.localizedNotes(for:"en") == "English update" && bilingualResult.localizedNotes(for:"zh") == "中文更新")
  let quiet = AppUpdater(defaults:defaults,currentVersion:current,endpoint:{endpoint},fetch:{_ in
   (equal,HTTPURLResponse(url:endpoint,statusCode:200,httpVersion:nil,headerFields:nil)!)
  })
  await quiet.check(manual:true)
  precondition(quiet.available == nil && quiet.status == "当前已是最新版本。")
  let failed = AppUpdater(defaults:UserDefaults(suiteName:suite+".offline")!,currentVersion:current,endpoint:{endpoint},fetch:{_ in throw URLError(.notConnectedToInternet)})
  defer { UserDefaults.standard.removePersistentDomain(forName:suite+".offline") }
  await failed.check(manual:false)
  precondition(failed.status.isEmpty && !failed.isDue())
  await failed.check(manual:true)
  precondition(failed.status == "检查更新失败，请检查网络后重试。")
  let httpFailure = AppUpdater(defaults:defaults,currentVersion:current,endpoint:{endpoint},fetch:{_ in
   (equal,HTTPURLResponse(url:endpoint,statusCode:503,httpVersion:nil,headerFields:nil)!)
  })
  await httpFailure.check(manual:true)
  precondition(httpFailure.detail.contains("503"))
  let badSchema = try JSONSerialization.data(withJSONObject:["schema_version":2])
  let schemaFailure = AppUpdater(defaults:defaults,currentVersion:current,endpoint:{endpoint},fetch:{_ in
   (badSchema,HTTPURLResponse(url:endpoint,statusCode:200,httpVersion:nil,headerFields:nil)!)
  })
  await schemaFailure.check(manual:true)
  precondition(schemaFailure.detail.contains("schema_version"))
  let downloadRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at:downloadRoot,withIntermediateDirectories:true)
  defer { try? FileManager.default.removeItem(at:downloadRoot) }
  let expectedHash = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
  func transfer()->UpdateTransfer {
   let config=URLSessionConfiguration.ephemeral;config.protocolClasses=[DownloadFixture.self]
   return UpdateTransfer(configuration:config)
  }
  let output=downloadRoot.appendingPathComponent("ok.dmg")
  let success=try await transfer().run(url:URL(string:"https://updates.example.invalid/ok")!,destination:output,sha256:expectedHash,size:3,progress:{_,_ in})
  let successBytes=try Data(contentsOf:success)
  precondition(successBytes == Data("abc".utf8))
  for (path,hash) in [("/ok",String(repeating:"0",count:64)),("/http",expectedHash)] {
   let target=downloadRoot.appendingPathComponent(UUID().uuidString)
   do { _ = try await transfer().run(url:URL(string:"https://updates.example.invalid"+path)!,destination:target,sha256:hash,size:3,progress:{_,_ in});fatalError("failed download accepted") }
   catch { precondition(!FileManager.default.fileExists(atPath:target.path) && !FileManager.default.fileExists(atPath:target.appendingPathExtension("part").path)) }
  }
  let cancelled=transfer();let cancelledTarget=downloadRoot.appendingPathComponent("cancel.dmg")
  let cancellation=Task { try await cancelled.run(url:URL(string:"https://updates.example.invalid/cancel")!,destination:cancelledTarget,sha256:expectedHash,size:3,progress:{_,_ in}) }
  try await Task.sleep(nanoseconds:50_000_000);cancelled.cancel()
  do {_=try await cancellation.value;fatalError("cancelled download accepted")}
  catch {precondition((error as? URLError)?.code == .cancelled && !FileManager.default.fileExists(atPath:cancelledTarget.path))}
  let precancelled = transfer();precancelled.cancel()
  do {_ = try await precancelled.run(url:URL(string:"https://updates.example.invalid/cancel")!,destination:cancelledTarget,sha256:expectedHash,size:3,progress:{_,_ in});fatalError("early cancellation ignored")}
  catch {precondition((error as? URLError)?.code == .cancelled)}
  do {_ = try await transfer().run(url:URL(string:"https://updates.example.invalid/ok")!,destination:cancelledTarget,sha256:expectedHash,size:2,progress:{_,_ in});fatalError("oversized download accepted")}
  catch {precondition(!FileManager.default.fileExists(atPath:cancelledTarget.path))}
  var releaseCount = 0
  let bound = AppUpdater(defaults:defaults,currentVersion:current,downloadRoot:downloadRoot,transferFactory:{transfer()},endpoint:{endpoint},fetch:{_ in
   releaseCount += 1
   let version = releaseCount == 1 ? "202610180901" : "202610180902"
   let body=try JSONSerialization.data(withJSONObject:["schema_version":1,"platforms":[AppUpdater.platform:["version":version,"url":"https://updates.example.invalid/ok","sha256":expectedHash,"size":3,"notes":"Bound release"]]])
   return (body,HTTPURLResponse(url:endpoint,statusCode:200,httpVersion:nil,headerFields:nil)!)
  })
  await bound.check(manual:true);bound.download()
  while bound.downloading {try await Task.sleep(nanoseconds:10_000_000)}
  precondition(bound.verifiedRelease?.version == "202610180901" && bound.downloaded != nil)
  await bound.check(manual:true)
  precondition(bound.available?.version == "202610180902" && bound.verifiedRelease?.version == "202610180901")
  print("Native offline update fixtures passed: five-hour persistence, restart, manual bypass, platform/version selection, HTTPS and hash validation, quiet automatic checks, visible manual results/errors")
 }
}
'''
with tempfile.TemporaryDirectory(prefix='BensonMail-updates-test-') as temporary:
    folder = Path(temporary)
    stub = folder / 'Fixtures.swift'
    stub.write_text(source)
    binary = folder / 'fixtures'
    subprocess.run(['swiftc', '-parse-as-library', str(project / 'Sources/BensonMailMac/Services/AppUpdater.swift'), str(project / 'Sources/BensonMailMac/Services/UpdateTransfer.swift'), str(stub), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
