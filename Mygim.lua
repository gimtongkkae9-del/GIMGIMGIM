<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- 1. 카카오톡에 표시될 카드 제목 -->
    <meta property="og:title" content="이동">
    
    <!-- 2. 카카오톡에 표시될 설명문 (필요 없으면 빈칸 가능) -->
    <meta property="og:description" content="클릭하면 해당 페이지로 이동합니다.">
    
    <!-- 3. 카카오톡 메세지에 띄울 이미지 URL -->
    <meta property="og:image" content="https://picsum.photos/800/400">
    
    <!-- 4. 대표 URL -->
    <meta property="og:url" content="https://example.com">

    <!-- 5. 접속 시 실제로 이동할 목적지 URL (리다이렉트 설정) -->
    <meta http-equiv="refresh" content="0; url=https://www.google.com">
    
    <title>이동 중...</title>
</head>
<body>
    <script>
        // 자바스크립트를 이용한 자동 이동 처리
        window.location.href = "https://www.google.com";
    </script>
    <p>페이지로 이동 중입니다...</p>
</body>
</html>
