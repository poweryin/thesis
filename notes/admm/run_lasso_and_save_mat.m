A = randn(100,100);
X = randn(100,80);
tic;
[B, cost] = lasso_admm(X, A , 1);
toc;
save('admm.mat', 'A', 'X', 'B', 'cost');
