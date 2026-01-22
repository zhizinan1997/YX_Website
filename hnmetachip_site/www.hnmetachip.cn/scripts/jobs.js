$(function () {
    
    $('.jobs_list li').click(function () {

        if ($(this).hasClass("active")) {
            $(this).removeClass('active');
            $(this).find('.jobs_hide').slideUp();
        }
        else {
            $(this).addClass('active').siblings().removeClass('active');
            $(this).find('.jobs_hide').slideDown();
            $(this).siblings().find('.jobs_hide').slideUp();
        }
    });

    $('.jobs_list li')[0].click();

})