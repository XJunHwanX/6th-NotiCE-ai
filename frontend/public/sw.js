/* NotiCE 웹 푸시 서비스워커.
 * - push: 서버가 보낸 푸시 데이터(title, body, url)를 알림으로 표시
 * - notificationclick: 알림 클릭 시 우리 서비스 홈으로 이동(열린 창 있으면 포커스, 없으면 새 창)
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

  // 원문 공지 URL 대신 우리 서비스 홈으로 이동시킨다.
  const homeUrl = new URL("/", self.location.origin).href;

  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      // 이미 열린 창이 있으면 홈으로 이동시키고 포커스
      for (const client of clientList) {
        if ("focus" in client) {
          if ("navigate" in client && client.url !== homeUrl) {
            try {
              await client.navigate(homeUrl);
            } catch {
              // 내비게이션 실패해도 포커스는 시도
            }
          }
          return client.focus();
        }
      }

      if (self.clients.openWindow) {
        return self.clients.openWindow(homeUrl);
      }
    })()
  );
});
