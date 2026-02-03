function bindJobsList() {
    const items = $('.jobs_list li');
    if (!items.length) return;

    items.off('click').on('click', function () {
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

    items.first().click();
}

$(function () {
    bindJobsList();
    window.initJobsList = bindJobsList;
});
