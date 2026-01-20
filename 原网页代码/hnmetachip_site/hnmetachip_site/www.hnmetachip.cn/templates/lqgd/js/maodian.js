//内容信息导航吸顶
$(document).ready(function(){ 
var navHeight= $("#navHeight").offset().top; 
var navFix=$("#nav-wrap"); 
var navHeights=$("#navHeight"); 
$(window).scroll(function(){ 
	if($(this).scrollTop()>navHeight){ 
		navHeights.addClass("navFix"); 
	} 
	else{ 
		navHeights.removeClass("navFix"); 
	} 
	}) 
})
//内容信息导航锚点
$('.nav-wrap').navScroll({
  mobileDropdown: true,
  mobileBreakpoint: 768,
  scrollSpy: true
});

$('.click-me').navScroll({
  navHeight: 0
});

$('.nav-wrap').on('click', '.nav-mobile', function (e) {
  e.preventDefault();
  $('.nav-wrap ul').slideToggle('fast');
});