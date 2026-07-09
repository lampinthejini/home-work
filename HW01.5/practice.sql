-- 전체 회원의 수를 구하라

select count(*)
  from customers c 
;

-- 전체 상품의 수를 구하라
select count(*)
  from products p 
;
--활성 회원의 수를 구하라
select count(*)
  from customers c 
 where c.is_active = 'true'
;
--비활성 회원의 수를 구하라
select count(*)
  from customers c 
 where c.is_active != 'true' 
 ;

-- 성별이 남성인 회원 수 구하기
select count(*)
  from customers c 
 where c.gender ='M'
;

-- VIP 등급 회원 수를 구하기
select count(*)
  from customers c 
 where c.grade = 'VIP'
;

 
-- 서울에 거주하는 회원 수 구하기
select count(*)
  from customers c 
 where c.city in ('서울')
 ;

 
 -- 상태가 '품절'인 상품 수를 구하라
select count(*)
  from products p 
 where p.status = '품절'
 ;
 
  -- 상태가 '단종'인 상품 수를 구하라
select count(*)
  from products p 
 where p.status = '단종'
 ;
  
  
-- 가장 비싼 상품 1개의 이름과 가격을 구하라
select p."name" 
	 , p.price 
  from products p 
 order by p.price desc 
 limit 1
;

-- 가장 싼 1개의 이름과 가격을 구하라
select p."name" 
	 , p.price 
  from products p 
 order by p.price asc 
 limit 1
;

-- 회원 이메일의 도메인 종류를 모두 구하라
SELECT DISTINCT split_part(email, '@', 2) AS 도메인
FROM customers
ORDER BY 도메인
 ;
  
-- 회원등급의 종류를 알파벳 순으로 구하라
 select distinct(c.grade)
   from customers c
  group by c.grade 
  order by 1 asc
;


-- 회원이 거주하는 도시는 몇 종류인가
select count(distinct(c.city))
  from customers c
;

-- 1990-01-01 이후 출생한 회원의 수를 구하라
select count(*)
  from customers c
 where date_trunc('month',c.birth_date)::date>= date '1990-01-01' 
 order by 1 asc
; 
 
 
-- 가격이 10만원 이상인 상품 수를 구하라
select count(*)
  from products p 
 where p.price >= 100000
 ;


-- 가격이 5만원 이상 10만원 이하인 상품 수를 구하라
 select count(*)
   from products p 
  where p.price between 50000 and 100000
  ;

-- 이메일이 gmail인 사람들의 수를 구하라
select count(*)
  from customers c 
 where c.email like '%gmail.com'
 ;

--이름이 '김'으로 시작하는 회원수를 구하라
select count(*)
  from customers c 
 where c.name like '김%'
 ;

-- 재고가 0인 상품 수를 구하라
select count(*)
  from products p 
 where p.stock_quantity = 0
;

-- 가장 비싼 상품 5개를 이름가격과 함께 구하라
select p."name" 
	 , p.price 
  from products p 
 order by p.price desc 
 limit 5
 ;

-- 가장 먼저 가입한 회원 5명을 이름 가입일과 함께 구하라
select c."name" 
	 , c.signup_date 
  from customers c 
 order by c.signup_date asc
 limit 5
 ;

 
 -- 등급별 회원의 수를 구하라
select c.grade 
	 , count(*)
  from customers c 
 group by c.grade 
;

-- 회원이 가장 많은 도시 5곳을 구하라
select c.city 
	 , count(*)
  from customers c 
 group by c.city
 order by 2 desc 
 limit 5
 ;

 -- 성별별 회원수
select c.gender 
	 , count(*)
  from customers c 
 group by c.gender   
 ;
 
 -- 상품 상태별 개수
 select p.status 
 	  , count(*)
   from products p 
  group by p.status 
 ;
  -- 분류(카테고리 id)별 상품수를 구하라
select p.category_id 
	 , count(*)
  from products p 
 group by p.category_id 
 order by p.category_id asc
 ;
 -- 분류별 평균 가격을 구하라
select p.category_id 
	 , round(avg(p.price),0) as 평균
  from products p 
 group by p.category_id 
;

 -- 전체 상품의 평균, 최저, 최고 가격을 한줄로 구하라
 select max(p.price)
 	  , min(p.price)
 	  , round(avg(p.price),0)
   from products p 
;

-- 등급별 가장 나이 많은 회원의 생년월일을 구하라
select c.grade 
	 , min(c.birth_date)
  from customers c 
 group by c.grade 
 
-- 2023년 상반기 (1~6월) 월별 주문 건수를 구하라
 select date_trunc('month',o.order_date )::date as month
	  , count(*)
   from orders o 
  group by date_trunc('month',o.order_date)::date
  order by 1 asc
  limit 6
 ;

-- 연도별 주문건수를 구하라
select date_trunc('year',o.order_date)::date as year
	 , count(*)
  from orders o
 group by 1
; 
 -- 주문 상태별 건수를 구하라
select o.status 
	 , count(*)
  from orders o
 group by o.status 
;

-- 배송지 별 주문 수 상위 5곳
select o.shipping_city 
	 , count(*)
  from orders o 
 group by o.shipping_city 
 order by 2 desc
 limit 5
  ;
  
-- 가격대 (저 5만 미만, / 중 20만 미만 / 고) 별 상품 수를 구하라

select case when p.price < 50000 then '저가'
			when p.price < 200000 then '중가'
			else '고가'
			end as 가격대
		, count(*)
  from products p 
 group by 1
 ;

 -- 상품수가 정확히 72개인 분류는 몇개인가?
select count(t)  
  from	(
  	select p.category_id  
		 , count(*)
	  from products p 
	 group by p.category_id 
	having count(*)= 72)t
;
-- 평균가가 185,000원 이상인 분류는 몇개인가
select count(t)
  from( 
  	select p.category_id 
		 , round(avg(p.price),0)
  	  from products p  
	 group by p.category_id 
	having avg(p.price)>=185000)t
;
-- 등급별 회원비율
select c.grade 
	 , round((count(*)/sum(count(*)) over())*100,1) as 비율
  from customers c 
 group by c.grade 
 ;
 

-- 재고 합계가 가장 큰 분류 5곳 구하라
select p.category_id 
	 , sum(p.stock_quantity)
  from products p 
 group by p.category_id 
 order by 2 desc 
 limit 5
 ;
 
-- 분류별 최고가 (어떤 건지 알 수 있을까?)
select p.category_id 
	 , max(p.price)
  from products p
 group by p.category_id
;

-- 가입연도 별 회원 수
select date_trunc('year',c.signup_date)::date as 가입연도
	 , count(*)
  from customers c 
 group by 1
 order by 1
;

-- 출생연대 별 회원수를 구하라.
select (floor(extract(year from c.birth_date)/10))*10::int as 연대
	 , count(*) as 회원수
  from customers c 
 group by 1
 order by 1
 ;

-- 분류별 '판매중' 상품수를 상위 6개 분류만 구해라
select p.category_id
	 , count(*) filter(where p.status = '판매중')
  from products p  
 group by p.category_id 
 order by 2 desc
 limit 6
 ;
-- 요일별 주문수를 구하라
SELECT extract(dow FROM order_date)::int AS 요일,
       count(*) AS 주문수
FROM orders
GROUP BY 1
ORDER BY 1;
 
 -- 평균가가 높은 분류 3곳을 구하라
select p.category_id 
	 , round(avg(p.price),0)
  from products p 
 group by p.category_id 
 order by 2 desc 
 limit 3
;

-- product_id 1 상품의 분류명을 구하라
select p."name" 
     , c."name" 
  from products p 
  join categories c on p.category_id = c.category_id 
 where p.category_id=1
 ;
-- 분류명이 '컴퓨터' 인 상품은 몇개인가?
select count(*)
  from products p 
  join categories c on p.category_id = c.category_id 
 where c."name" ='컴퓨터';

-- 컴퓨터 분류 상품의 평균 가격을 구하라
select round(avg(p.price),0)
  from products p 
  join categories c on p.category_id = c.category_id 
 where c."name" ='컴퓨터';

-- 분류별 매출 상위 5를 구하라
select c."name" 
	 , sum(oi.quantity *oi.unit_price)
  from products p 
  join categories c on p.category_id = c.category_id
  join order_items oi on oi.product_id = p.product_id 
 group by c.category_id 
 order by 2 desc 
 limit 5
 ;

-- 주문을 가장 많이 한 회원 5명을 이름과 함께 구하라
select c."name" 
	 , count(*)
  from orders o
  join customers c  on c.customer_id = o.customer_id 
 group by c.customer_id 
 order by 2 desc 
 limit 5;
 
 -- 총 구매액 상위 회원 5명을 구하라
 select c."name" 
 	  , sum(o.total_amount )
   from orders o
   join customers c on c.customer_id =o.customer_id 
  group by c.customer_id ,c."name" 
  order by 2 desc 
  limit 5;
 
-- order 12345 주문의 품목(상품명,수량,단가)을 구하라
select p."name"  as 상품명
	 , oi.quantity as 수량
	 , oi.unit_price  as 단가
  from order_items oi 
  join products p on oi.product_id =p.product_id 
 where oi.order_id = 12345;
 
 -- customer_id= 1 회원의 주문 수를 구하라
select count(*)
  from orders o 
 where o.customer_id = 1;

-- 분류별 주문건수 (중복제거) 상위 5를 구하라.
select c."name" 
     , count(distinct(oi.order_id))
  from order_items oi 
  join products p on p.product_id = oi.product_id 
  join categories c on p.category_id =c.category_id 
 group by c."name"  
 order by 2 desc 
 limit 5;
 
-- 분류별 '단종' 상품수를 0 포함해 구하라
select c."name" 
	 , count(p.product_id)
  from categories c 
  left join products p on c.category_id =p.category_id and p.status ='단종'
 group by c.category_id ;

-- 배송지 도시별 매출 상위 5를 구하라
select o.shipping_city 
	 , sum(oi.unit_price *oi.quantity)
  from order_items oi 
  join orders o  on o.order_id = oi.order_id 
 group by o.shipping_city  
 order by 2 desc 
 limit 5;
 
 -- vip 회원이 낸 주문은 총 몇건인가?
select count(*)
  from customers c 
  join orders o on c.customer_id  = o.customer_id 
 where c.grade='VIP';
 
 -- 등급별 평균 주문액을 구하라
select distinct c.grade 
	 , round(avg(o.total_amount) over(partition by c.grade),0)
  from orders o
  join customers c on o.customer_id = c.customer_id 
 order by 2 desc 
 ;
 
 -- 2023년 상반기 월별 매출액을 구하라.
   select extract(month from o.order_date) as 월
  	   , sum(o.total_amount)
  	from orders o
   where floor(extract(year from o.order_date))=2023
   	 and extract(month from o.order_date)<= 6
   	 and o.status not in ('취소','환불')
   group by 1
 ;  
   
 -- 상품별 주문 수량 상위 5를 구하라
 select p."name"   
 	  , round(avg(oi.quantity),2)
   from order_items oi 
   join products p  on oi.product_id =p.product_id 
  group by p.product_id 
  order by 2 desc
  limit 5;
  
-- 한번도 팔리지 않은 상품 수를 구하라
select p."name" 
	 , sum(oi.quantity)
  from order_items oi 
  join products p on oi.product_id = p.product_id
 group by p.product_id
having 2 = 0;

select count(*) as 미판매상품수
  from products p
 where not exists( select 1 from order_items oi where oi.product_id = p.product_id);
 
-- 주문 1건당 평균 품목 수를 구하라
with perord as (select oi.order_id 
	 , count(*) as 일별주문량
  from order_items oi 
 group by oi.order_id )
select avg(일별주문량)
  from perord per;
  
 -- 전체 평균가보다 비싼 상품 수를 구하라
select count(*)
  from products p2 
  where p2.price >(select avg(p.price)
  			from products p);
 --전체 평균가보다 비싼 상품 중 가장 싼 것을 구하라
select p2."name" 
  from products p2
 where p2.price >(select avg(p.price)
 			from products p)
 order by p2.price asc, p2.product_id asc
 limit 1;
 
 --각 분류에서 가장 비싼 상품을 분류 1~5만 구하라.
 with mx as (select p.category_id 
 		  , max(p.price) as 최대값
   		from products p 
  		group by p.category_id) 
 select p2.category_id 
 	  , p2."name" 
 	  , p2.price
   from products p2 
   join mx on p2.category_id = mx.category_id and p2.price=최대값
  order by p2.category_id asc 
  limit 5;
  
  -- 전체 평균 주문액보다 큰 주문은 몇 건인가?
select count(*)
  from orders o2
  where o2.total_amount >
  (select avg(o.total_amount)
     from orders o );
  
  
-- 주문 이력이 있는 VIP의 수를 구하라
select count(*)
  from customers c 
  where c.grade ='VIP'
    and exists (select 1 
 		  from orders o 
 		 where o.customer_id =c.customer_id );
 

--최고가 상품과 같은 분류에 속한 상품은 몇 개인가
select count(*)
  from products p3 
 where p3.category_id in
(select p.category_id
   from products p 
  where p.price = (
 	select max(p2.price) 
 	  from products p2));

-- 모범 답안
SELECT count(*) AS cnt
FROM products
WHERE category_id = (
  SELECT category_id FROM products
  ORDER BY price DESC, product_id LIMIT 1
);

--최고가와 같은 가격을 가진 상품은 몇 개인가?
select count(*)
  from products
 where price =(select max(price)
  					from products)
 ;

-- 단종 상품이 하나도 없는 분류
select category_id 
 from products
where category_id not in (select category_id 
              from products 
              where status = '단종')
group by category_id;


SELECT category_id FROM products WHERE status = '판매중'
EXCEPT
SELECT category_id FROM products WHERE status = '단종'
ORDER BY category_id;

-- 판매중 상품과 단종 상품이 모두 있는 분류를 구하라
select p.category_id 
  from products p 
 where p.status ='판매중'
 intersect 
 select p.category_id
   from products p 
  where p.status ='단종'
 order by category_id asc;
 
 -- 월 매출의 평균(월 평균 매출)을 구하라
with monthearn as (select date_trunc('month',o.order_date)::date
	 , sum(o.total_amount) as monthsum
  from orders o
 group by date_trunc('month',o.order_date))
 select round(avg(me.monthsum),0) as monthavg from monthearn me;
 
 WITH m AS (
  SELECT date_trunc('month', order_date) AS 월, sum(total_amount) AS 매출
  FROM orders GROUP BY 1
)
SELECT round(avg(매출)) AS 월평균매출 FROM m;

-- 총 구매액이 전체 회원 평균보다 큰 회원은 몇명인가?

with co as (select o.customer_id as id_num 
	 , sum(o.total_amount)as total
  from orders o 
 group by o.customer_id )
select count(*) as avgup_people
  from co
 where co.total> (select avg(co.total) from co)
;

 
-- 상품 가격의 중앙값을 구하라
  SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY price) AS 중앙값
FROM products;
 

-- 평균가가 전체 평균가보다 높은 분류는 몇개인가?
with avc as (select p.category_id 
	 ,  avg(p.price)as average_p
  from products p 
 group by p.category_id )
 select count(*)
   from avc
  where avc.average_p > (select avg(price) from products)
  
  SELECT count(*) AS 분류수
FROM (
  SELECT category_id FROM products GROUP BY category_id
  HAVING avg(price) > (SELECT avg(price) FROM products)
) t;


-- 주문액 상위 10% 경계값 (90 백분위)을 구하라
with perc as(select o.total_amount,
ntile(10) over(order by o.total_amount desc) as nt
  from orders o)
select min(perc.total_amount) as 경계값
  from perc
 where perc.nt = 1
--틀린 문제 하지만 답은 틀리지 않았다.
-- 답지
select round(percentile_cont(0.9) within group (order by total_amount)) as p90
 from orders;
 
 
 -- 분류별 가격 Top 3를 (분류 1~2만) 구하라
--select p.category_id
--	 , sum(p.price)
--	 , rank() over(order by sum(p.price) desc)
--  from products p 
-- group by p.category_id 
-- limit 3

select *
  from (select p."name" 
	 , p.category_id, p.price 
	 , rank() over(partition by p.category_id order by p.price desc) as rnk
  from products p)t
  where rnk<=3 and t.category_id in(1,2)
  order by category_id, rnk asc
;

select p."name" 
	 , p.price 
	 , row_number() over(order by p.price desc, p.product_id) as rnk
  from products p 
 limit 5
 
  --2023년 상반기 월매출 누적합
with  ma as (select date_trunc('month',o.order_date)::date as mon,
  sum(o.total_amount) as sum_mon
  from orders o
 where floor(extract('year' from o.order_date))=2023
   and floor(extract('month' from o.order_date))<=6
   and o.status not in('환불','취소')
  group by date_trunc('month',o.order_date)::date)
select ma.mon
	 , ma.sum_mon
	 , sum(ma.sum_mon) over(order by ma.mon asc)
  from ma
  
  --2023년 상반기 원매출 전월대비 증감을 구하라 
 with  ma as (select date_trunc('month',o.order_date)::date as mon,
  sum(o.total_amount) as sum_mon
  from orders o
 where o.order_date>=date '2023-01-01'
   and o.order_date<date '2023-07-01'
   and o.status not in('환불','취소')
  group by date_trunc('month',o.order_date)::date)
select ma.mon
	 , ma.sum_mon
	 , ma.sum_mon-lag(ma.sum_mon) over(order by ma.mon asc) as const_last
  from ma
   
  
  WITH m AS (
  SELECT date_trunc('month', order_date)::date AS 월, sum(total_amount) AS 매출
  FROM orders GROUP BY 1
)
SELECT 월, 매출, 매출 - lag(매출) OVER (ORDER BY 월) AS 전월대비
FROM m ORDER BY 월 LIMIT 6;

-- 상품을 가격 사분위(ntile 4)로 나눠 분위별 상품수 가격범위를 구하라
select count(*)
	 , t.f_per 
	 , max(t.price)
	 , min(t.price)
  from (select "name"
	 , ntile(4) over(order by price asc) as f_per
	 , price 
  from products)t
  group by t.f_per
  order by t.f_per asc
  
  
SELECT 사분위, count(*) AS 상품수, min(price) AS 최소, max(price) AS 최대
FROM (
  SELECT price, ntile(4) OVER (ORDER BY price) AS 사분위 FROM products
) t
GROUP BY 사분위 ORDER BY 사분위;

-- 분류 1번 안에서 각 상품의 가격 비중(%) 상위 5를 구하라
select p."name" 
	 , p.price 
	 , (p.price / sum(p.price) over() )*100 as perc
	 , rank() over(order by p.price desc) as rnk
  from products p 
 where p.category_id=1
 order by 3 desc, p.product_id asc
 limit 5;
 
 SELECT name, price,
       round(100.0 * price / sum(price) OVER (PARTITION BY category_id), 3) AS 분류내비중
FROM products
WHERE category_id = 1
ORDER BY price DESC
LIMIT 5;

with total_customer as (select customer_id 
	 , sum(total_amount) as sum_a
  from orders
 group by customer_id )
 select t.n10 
  	  ,	count(*)
 	  , max(t.sum_a)
 	  , min(t.sum_a)
   from (select tc.customer_id
 	 ,  tc.sum_a,
 ntile(10) over(order by tc.sum_a) as n10
   from total_customer tc)t
   group by t.n10 
   order by max(t.sum_a) asc ;

--분류 1번에서 각 상품 가격이 분류 평균과 얼마나 차이나는지 상위 5를 구하라.
select p."name" 
	 , p.price 
	 , avg(p.price) over(partition by p.category_id) as aver
	 , p.price-avg(p.price) over(partition by p.category_id)  as differ
  from products p 
 where p.category_id =1
 order by differ desc 
 limit 5;
 
 SELECT name, price,
       round(avg(price) OVER (PARTITION BY category_id)) AS 분류평균,
       round(price - avg(price) OVER (PARTITION BY category_id)) AS 편차
FROM products
WHERE category_id = 1
ORDER BY price DESC
LIMIT 5;


-- 가입 연도별 누적 회원 수
select floor(extract('year'from c.signup_date))
	 , count(*)
	 , sum(count(*)) over(order by floor(extract('year'from c.signup_date)) asc)
  from customers c 
 group by floor(extract('year'from c.signup_date))
 order by 1 asc;
 
 --가격 동률을 함께 묶는 순위(dense_rank)로 상위 5행을 구하라.
select p. name, p.price
	 , dense_rank() over(order by p.price desc) as samernk
   from products p 
  order by p.price desc, p.product_id asc   
  limit 5;

 --가격 내림차순에서 바로 다음 상품과의 가격 차이를 상위 5개 구하라.
select p."name" 
	 , p.price
	 , p.price - lead(p.price) over(order by p.price desc, p.product_id asc) as price_diff
  from products p 
  order by p.price desc, p.product_id asc
  limit 5
  
--분류 1번에서 가격 백분위(percent_rank)가 0.9 이상인 상위 상품을 구하라.
select t."name", t.price , round(t.percent_price_rank::numeric,2)
  from (select p."name" 
	 , p.category_id 
	 , p.price 
	 , (percent_rank() over(order by p.price asc, p.product_id asc))*100 as percent_price_rank
  from products p
  where p.category_id = 1)t
  where t.percent_price_rank >=90
 order by percent_price_rank desc;
 
 
 SELECT name, price, round(pr::numeric, 3) AS 백분위
FROM (
  SELECT name, price, category_id,
         percent_rank() OVER (PARTITION BY category_id ORDER BY price) AS pr
  FROM products
) t
WHERE category_id = 1 AND pr >= 0.9
ORDER BY pr DESC
LIMIT 5;
 
 
 
 
 -- 2023년 상반기 월별 매출 추세를 (월, 매출, 누적, 전월 대비) 한번에 구하라
-- 필요 요건 월 추출, 매출(sumprice), 누적(sumorderby),전월대비(lag)
with month_amount as (
	select date_trunc('month',o.order_date ) as month
		 , sum(o.total_amount ) as summ
	  from orders o
	 group by date_trunc('month',o.order_date )
	 order by 1 asc)
select ma."month" 
	 , ma.summ 
	 , sum(ma.summ) over(order by ma."month" asc) as accumulation
	 , ma.summ - lag(ma.summ) over(order by ma."month"  asc) as month_diff 
  from month_amount ma
 where ma."month" >= date '2023-01-01'
   and ma."month" < date '2023-07-01';
 
 
WITH m AS (
  SELECT date_trunc('month', order_date)::date AS 월, sum(total_amount) AS 매출
  FROM orders WHERE order_date < DATE '2023-07-01' GROUP BY 1
)
SELECT 월, 매출,
       sum(매출) OVER (ORDER BY 월) AS 누적,
       매출 - lag(매출) OVER (ORDER BY 월) AS 전월대비
FROM m ORDER BY 월;

-- 분류별 매출과 전체 대비 비중(%)을 구하라
-- 분류별 매출, 전체 대비 비중(분류별매출/총매출(over를 써서))
select c."name"
	 , sum(oi.quantity *oi.unit_price) as category_sum
	 , round(sum(oi.quantity *oi.unit_price) / (sum(sum(oi.quantity *oi.unit_price)) over())*100,2) as percent_cat
  from products p 
  join categories c on p.category_id = c.category_id 
  join order_items oi on p.product_id = oi.product_id 
 group by c."name" 
 order by c."name" asc;
 
 
--매출 상위 10개 상품이 전체 매출에서 차지하는 비중(%)을 구하라.
-- 상품, 매출(oi)에서 추출, 상위 10개, 비중(매출/전체매출)
select p."name" 
	 , sum(oi.quantity*oi.unit_price) as product_amount
	 , dense_rank() over(order by sum(oi.quantity*oi.unit_price) desc, p."name" asc) as product_ranking
	 , round(100.0 *sum(oi.quantity *oi.unit_price) /sum(sum(oi.quantity *oi.unit_price)) over(),2) as percent_products
  from products p 
  join order_items oi on oi.product_id = p.product_id 
 group by p.product_id
 limit (10)
 
 --추가 전체 매출에서 차지하는 비중 추가
select round(sum(t.percent_products),2) as amount_percent
  from(
	  select p."name" 
		 , sum(oi.quantity*oi.unit_price) as product_amount
		 , dense_rank() over(order by sum(oi.quantity*oi.unit_price) desc, p."name" asc) as product_ranking
		 , 100.0 *sum(oi.quantity *oi.unit_price) /sum(sum(oi.quantity*oi.unit_price)) over() as percent_products
	  from products p 
	  join order_items oi on oi.product_id = p.product_id 
	 group by p.product_id 
	 order by percent_products desc, p."name" asc
	 limit (10))t;
 
 WITH s AS (
  SELECT product_id, sum(quantity * unit_price) AS rev
  FROM order_items GROUP BY product_id
)
SELECT round(100.0 *
  (SELECT sum(rev) FROM (SELECT rev FROM s ORDER BY rev DESC LIMIT 10) a)
  / (SELECT sum(rev) FROM s), 2) AS 상위10_비중pct;
 
 
--2024년에 가입한 신규 회원 수를 구하라.
select count(*) as "2024signup"
  from customers c 
 where extract('year' from c.signup_date)=2024;
 
 SELECT count(*) AS 신규회원
FROM customers
WHERE extract(year FROM signup_date) = 2024;


-- 주문을 2건이상 한 회원(재구매 고객)은 몇명인가?
-- 주문을 다 각자 몇건씩 했는지
-- 2건 이상 한 회원만 추출
select count(*)
  from (
	  select o.customer_id 
		 , count(*) as order_count
	    from orders o 
	   group by o.customer_id)t
  where t.order_count >=2;
  
  
  select count(*)
  from (
	  select o.customer_id 
		 , count(*) as order_count
	    from orders o 
	   group by o.customer_id
	  having count(*)>=2)t;

 percentile_cont(0.8) WITHIN GROUP (ORDER BY 
 
 -- 매출 누적비중이 80% 이하에 드는 (상위)상품은 몇개?
 -- 누적을 높은데서부터 낮은데로 매출 비중. 
 -- 누적해서 80%까지 자른다.
with amounts as (
				select oi.product_id 
			 	  , sum(oi.quantity * oi.unit_price) as products_amount
			 	  , 100* SUM(oi.quantity*oi.unit_price) / sum(sum(oi.quantity*oi.unit_price)) over() as per_amount
			      from order_items oi
			     group by oi.product_id
			     order by SUM(oi.quantity*oi.unit_price) desc, oi.product_id)
 select count(*)
  from (select am.product_id 
			 , sum(am.per_amount) over(order by am.products_amount desc, am.product_id asc) as percents
		  from amounts am)t
 where t.percents<=80;
 
 -- 답지
 WITH s AS (
  SELECT product_id, sum(quantity * unit_price) AS rev FROM order_items GROUP BY product_id
),
r AS (
  SELECT product_id, rev,
         sum(rev) OVER (ORDER BY rev DESC, product_id) AS cum,
         sum(rev) OVER () AS tot
  FROM s
)
SELECT count(*) AS 상품수_누적80
FROM r WHERE cum <= 0.8 * tot;
 

--가입 연월별 회원 수 상위 5개월
select t.yearmonth
	 , dense_rank() over (order by t.count_signup desc)
	 , t.count_signup
  from(
	  select date_trunc('month',c.signup_date)::date as yearmonth
		 , count(*) as count_signup
	    from customers c 
	   group by date_trunc('month',c.signup_date)::date)t
 order by t.count_signup desc, t.yearmonth asc
  limit 5;
  
  SELECT date_trunc('month', signup_date)::date AS 가입월, count(*) AS 회원수
FROM customers
GROUP BY 1
ORDER BY 회원수 DESC, 가입월
LIMIT 5;
  
-- 등급별 회원수 주문수 객단가(평균주문액)를 한번에 구하라
-- 등급별 회원수, 주문수, 평균주문액(총주문액/회원수)

select c.grade
	 , count(distinct c.customer_id) as count_customer
	 , count(*) as count_order
	 , round(avg(o.total_amount),2)
  from customers c
  join orders o on c.customer_id =o.customer_id 
  group by c.grade
  order by count_customer asc
  
  SELECT cu.grade,
       count(DISTINCT cu.customer_id) AS 회원수,
       count(o.order_id)            AS 주문수,
       round(avg(o.total_amount))   AS 객단가
FROM customers cu
JOIN orders o ON o.customer_id = cu.customer_id
GROUP BY cu.grade
ORDER BY 객단가 DESC;