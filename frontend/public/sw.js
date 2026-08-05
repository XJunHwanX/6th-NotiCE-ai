/* NotiCE 웹 푸시 서비스워커.
 * - push: 서버가 보낸 푸시 데이터(title, body, url)를 알림으로 표시
 * - notificationclick: 알림 클릭 시 공지 URL로 이동(열린 탭 있으면 포커스, 없으면 새 탭)
 * public/ 아래 파일이라 번들링되지 않고 /sw.js 로 그대로 서빙됩니다.
 */

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    // JSON이 아니면 본문 텍스트로 취급
    payload = { body: event.data ? event.data.text() : "" };
  }

  const title = payload.title || "NotiCE 새 공지";
  const options = {
    body: payload.body || "새로운 공지가 등록되었어요.",
    // TODO(design): 아이콘 에셋 준비되면 지정 (icon: "/icon-192.png", badge: "/badge-72.png")
    data: { url: payload.url || "/" },
    tag: payload.tag, // 같은 tag의 알림은 갱신됨(선택)
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const raw = (event.notification.data && event.notification.data.url) || "/";
  // 상대 경로도 절대 URL로 정규화해서 정확히 비교
  const targetUrl = new URL(raw, self.location.origin).href;

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      for (const client of clientList) {
        if (client.url === targetUrl && "focus" in client) {
          return client.focus();
        }
      }

      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })()
  );
});
