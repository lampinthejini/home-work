# 필요한 외장함수 불러오기
import pickle
# import glob 안써도됨
import re
import os #현재 디렉토리를 찾기 위한 함수
# 데이터 빈 리스트 지정.(예외처리로 진행)
# members= []

# 데이터 불러오기에 대한 함수
def load_data(path):
    f= open(f"{path}/members.dat",'rb')
    members = pickle.load(f)
    return members



# 프린트 메뉴에 관한 함수
def print_menu():
    print("="*30)
    print("  다음 메뉴 중 하나를 선택하세요.")
    print("="*30)
    print("""
          1. 회원 추가
          2. 회원 목록 보기
          3. 회원 정보 수정하기
          4. 회원 삭제
          5. 종료
          """)


# 메인 선택창에 관한 함수
def main():
    while True:
        print_menu()
        num = input("1~5번 숫자를 입력해주세요.")
        if num == '1' : # 추가에 대한 함수 def add_member 참조
            add_member(members)
            print("추가되었습니다.")
            continue #컨티뉴를 통한 초기main함수 시행
        if num == '2' : # 목록보기에 대한 함수 def add_member 참조
            try:
                list_member(members)
            except Exception:
                print("등록된 번호가 없습니다.")
            continue
        if num == '3' : # 수정에 대한 함수 def add_member 참조
                name = input("수정할 회원의 이름을 입력하세요.")
                try: 
                    update_member(members,name)
                except Exception as e:
                    print(e)
                    continue
                print("수정이 완료되었습니다.")
                continue
        if num == '4' :
            name = input("삭제할 회원의 이름을 입력하세요.")
            try:
                delete_member(members,name)
            # 3번과 마찬가지로 중복확인 후, delete시행
            except Exception as e:
                print(e)
                continue
            print("삭제가 완료되었습니다.")
            continue
        if num == '5' :
            #파일로 세이브하고 종료하는 과정.
            save_data(os.getcwd(),members)
            break
        else:
            try:
                raise Exception("잘못된 입력입니다. 다시 선택하세요.")
            except Exception as e:
                print(e)


def add_member(members):
    member = input_member()
    members.append(member)
    return members

def input_member():
    while True:
        try:
            name = input("이름 :")
            validate_name(name) # 이름 유효성 검사 함수
        except Exception:
            print("이름은 1자 이상, 5자 이하만 가능합니다.")
            continue
        while True:
            try:
                phone=input("전화번호 (ex: 01012345678) :")
                validate_phone(phone) #번호 유효성 검사 함수
            except Exception as e:
                print(e)
                continue
            address=input("주소 :") # 주소는 바로 넣는걸로.
            while True:
                try: 
                    type_=input("종류 (ex. 가족, 친구, 기타) :")
                    validate_type(type_) #구분 유효성 검사 함수
                except Exception:
                    print("구분은 가족/친구/기타 중 하나여야 합니다.")
                    continue
                break
            break
        break
    return {"name":name,"phone":phone,"address":address,"type":type_}
        


def validate_name(name):
    #이름은 0자 안되고, 5자이상 안됨.
    if 0<len(name.strip())<=5:
        pass
    else:
        raise Exception

def validate_phone(phone):
    # 전화번호 형식이 안적혀질 경우 예외처리
    pat_num=r"^010\d{8}$"
    pat = re.compile(pat_num)
    if pat.search(phone) == None:
        raise Exception("번호가 유효하지 않습니다.")
    else:
        #중복 번호 점검
        for member_phone in members:
            if member_phone["phone"]==phone:
                    raise Exception("중복된 번호입니다.")

def validate_type(t):
    # 타입을 검사하고, 타입 값이 나오기 위한 함수
    if all([t!= "가족",t!= "친구",t!= "기타"]):
        raise Exception
    
def list_member(members):
    # 리스트 멤버를 리스트로 나열하는 함수
    if len(members)>0:
        print(f"총 {len(members)}명의 회원이 저장되어 있습니다.")
        for num in range(0,len(members)):
            print(f"회원정보 : 이름 = {members[num]["name"]}, 전화번호 : {members[num]["phone"]}, 주소 : {members[num]["address"]}, 구분 : {members[num]["type"]}")
    else:
        raise Exception

def find_by_name(members:list,name):
    samename=[] #몇명의 이름이 있는지 검색
    count=0
    indexnum=0
    for indexnum in range(len(members)):
        if members[indexnum-count]["name"] == name:
            samename.append(members.pop(indexnum-count))
            count+=1
        #이름이 일치하는 사람 수를 체크하기 위함.
    return samename #반환값을 namecount로 활용해서 main함수 및 업데이트 / 삭제에 활용
            
def update_member(members:list,name):
    samename= find_by_name(members,name)
    #멤버가 얼마나 있는지에 대한 점검.
    if len(samename)==0:
        raise Exception("해당하는 회원 정보가 없습니다.")
    elif len(samename) == 1 :
            samename.pop(0)
            print("수정할 정보를 입력하세요.")
            add_member(members)
    else:
        print(f"총 {len(samename)}개의 목록이 검색되었습니다.")
        while True:
            print("아래 목록 중 수정할 회원의 번호를 입력하세요.")
            # 같은 이름에 있는 사람들을 리스트로 묶어두고, 호출할 예정, 
            # 카운트는 pop으로 빼내면, 그만큼 함수 수가 줄어들어서 함께 체크하기 위함. 
            for count in range(len(samename)):
                print(f"{count+1}. 이름 = {samename[count]["name"]}, 전화번호 : {samename[count]["phone"]}, 주소 : {samename[count]["address"]}, 종류 :{samename[count]["type"]}")
            try:
                number = input()
                if number not in [str(number) for number in range(1,len(samename)+1)]: # 인풋은 문자열이므로, 번호 선택이 잘됐는지 문자열로 체크
                    raise Exception("잘못된 입력입니다. 다시 선택해주세요.")
            except Exception as e:
                print(e)
                continue
            print("수정할 정보를 입력하세요.") #이후 점검이 끝나면 바로 수정
            break
        samename.pop(int(number)-1) # 원래 있던 딕셔너리를 삭제하고, 추가로 멤버를 만드는 방식
        members.extend(samename) # 모아둔 동명이인 멤버에 복귀
        add_member(members)

            

def delete_member(members:list,name): #멤버를 삭제하는 함수
    samename= find_by_name(members,name)
    #멤버가 얼마나 있는지에 대한 점검.
    if len(samename)==0:
        raise Exception("해당하는 회원 정보가 없습니다.")
    elif len(samename) == 1 : # 반복문 통해서  점검해서 연락처 딕셔너리를 제거할 예정.
            samename.pop(0) #제거할 함수.
    else: #동명이인 리스트 및 선택 삭제
        print(f"총 {len(samename)}개의 목록이 검색되었습니다.")
        while True:
            print("아래 목록 중 삭제할 회원의 번호를 입력하세요.")
            count=0
            for count in range(len(samename)):              
                print(f"{count+1}. 이름 = {samename[count]["name"]}, 전화번호 : {samename[count]["phone"]}, 주소 : {samename[count]["address"]}, 종류 :{samename[count]["type"]}")
            try:        
                number = input()
                if number not in [str(number) for number in range(1,len(samename)+1)]:
                    raise Exception("잘못된 입력입니다. 다시 선택해주세요.")
            except Exception as e:
                print(e)
                continue
            break
        samename.pop(int(number)-1)
        members.extend(samename)

        
def save_data(path,members): #피클을 통한 덤핑 및 os현재 디렉토링을 이용한 path활용
    f= open(f"{path}/members.dat",'wb')
    pickle.dump(members,f)
    f.close()
    print("종료되었습니다.")
        

        

#멤버스 파일이 있을 때, 바로 데이터 불러오기 진행.
# if len(list(glob.glob("./members.dat")))==1:
#     members=load_data()

#에러점검 및 비어있는 리스트 생성. os 현재 디렉토리 작성.
try :
    members=load_data(os.getcwd())
except (FileNotFoundError,EOFError,pickle.UnpicklingError) :
    print("파일 혹은 데이터가 존재하지 않습니다. 비어있는 데이터로 시작합니다.")
    members= []    

#함수 실행
main()




