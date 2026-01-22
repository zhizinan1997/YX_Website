
	 var swiper = new Swiper('.section1 .swiper-container', {
		pagination: '.section1 .swiper-pagination',
		slidesPerView:1,
		paginationClickable: true,
		spaceBetween:0,
		loop: true,
		autoplay: 4500,
		autoplayDisableOnInteraction: false,
		speed:1000
	});	

	 var swiper = new Swiper('.index_product_all .swiper-container', {
		nextButton: '.index_product_all .swiper-button-next',
		prevButton: '.index_product_all .swiper-button-prev',
		slidesPerView:3,
		paginationClickable: true,
		spaceBetween:14,
		loop: true,
		autoplay: 2500,
		autoplayDisableOnInteraction: false,
		speed:500
	});	
	
	
	 var swiper = new Swiper('.section5_liucheng .swiper-container', {
		 nextButton: '.section5_liucheng .swiper-button-next',
        prevButton: '.section5_liucheng .swiper-button-prev',
		slidesPerView:5,
		paginationClickable: true,
		spaceBetween:0,
		loop: true,
		autoplay: 4500,
		autoplayDisableOnInteraction: false,
		speed:700
	});
	
	
	 var swiper = new Swiper('.section6_all .swiper-container', {
		nextButton: '.section6_all .swiper-button-next',
		prevButton: '.section6_all .swiper-button-prev',
		slidesPerView:3,
		paginationClickable: true,
		spaceBetween:0,
		loop: true,
		autoplay: 2500,
		autoplayDisableOnInteraction: false,
		speed:500
	});	
	
	
	//弹出视频
	var myvideo = document.getElementsByTagName('video')[0];
	$(".ab_video").click(function(){
		$(".video_bj").css("display","block");
		myVideo.play();
	});


	$(".close").click(function(){
		$(".video_bj").css("display","none")
        myvideo.pause();
	});
