# 연락처 관리 웹서비스 TRD

이 문서는 FastAPI 기반 연락처 관리 웹서비스를 구현하기 위한 기술 요구사항 정의서(TRD)입니다.

**Version:** 3.2  
**Last Updated:** 2026-07-09

---

## Version History

- **v1** : 상세 TRD 작성
- **v2** : ADS 형태로 구조 개선
- **v3** : 상세 TRD와 ADS 통합
- **v3.1** : 다이어그램 및 화면 설계 추가
- **v3.2** : 정책, 부록, AI 판단 기준 보완

---

## References

본 문서는 다음 자료를 기반으로 작성되었습니다.

- 과제 목적
- 구현 요구사항
- 화면 정의서
- 기능 정의서
- PRD(Project Requirements Document)

또한 AI(ChatGPT, Claude Code)를 활용하여 문서의 구조를 개선하고, 기술 명세의 일관성을 검토하였습니다.

---

## launch

run_desktop.py를 실행하면 파일 실행 완료입니다. requirements.txt파일에 있는 파일은 반드시 설치해야합니다. pip install -r requirements.txt 실행하면 적용이 됩니다. .env가 없으면 실행이 되지 않습니다. 참고해주세요!

docker에서 다음과 같은 명령을 해서 컨테이너를 생성해주세요. 패치 바로 하도록 하겠습니다. 
docker run -d `
  --name hw02-postgres `
  -e POSTGRES_USER=user `
  -e POSTGRES_PASSWORD=password `
  -e POSTGRES_DB=contact_db `
  -p 5432:5432 `
  postgres:16
